#!/usr/bin/env python
import glob
import os
import argparse
from collections import defaultdict, Counter
import configparser
from multiprocessing import Pool
from ete3 import Tree, TreeStyle, NodeStyle, TextFace
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
plt.style.use('ggplot')


def parse_metadata(metadata, input_metadata=None):
    metadata_comb = {}
    tax_col = {}
    for line_ in open(metadata):
        if 'Full Name' not in line_:
            sline = line_.split('\t')
            tax = sline[0].strip()
            group = sline[2].strip()
            col = sline[4].strip()
            sub_tax = sline[3]
            full = sline[1].strip()
            if group not in tax_col:
                if col.lower() in ['x', 'xx']:
                    col = 'white'
                tax_col[group] = col
            metadata_comb[tax] = {'group': group, 'col': tax_col[group], 'full': full, 'subtax': sub_tax}
    if input_metadata:
        for line in open(input_metadata):
            if "FILE_NAME" not in line:
                metadata_input = line.split('\t')
                tax = metadata_input[2].strip().split('_')[0]
                group = metadata_input[3].strip()
                full = metadata_input[6].strip()
                sub_tax = metadata_input[4]
                metadata_comb[tax] = {'group': group, 'col': "white", 'full': full, 'subtax': sub_tax}
    return metadata_comb, tax_col


def suspicious_clades(tree):
    t = Tree(tree)
    R = t.get_midpoint_outgroup()
    t.set_outgroup(R)

    supported_clades = []
    for node in t.traverse('preorder'):
        if (node.is_root() is False) and (node.is_leaf() is False):
            if node.support >= 70 and (len(node) < (len(t)-len(node))):
                clade = node.get_leaf_names()
                if len(clade) > 1:
                    supported_clades.append(clade)
    suspicious = []
    for clade in supported_clades:
        groups = set()
        for org in clade:
            if '..' in org:
                org = org.split('..')[0]
            else:
                org = org.split('_')[0]
            groups.add(metadata[org]['group'])
        if len(groups) > 1:
            suspicious.append(clade)
    return tree, suspicious


def get_best_candidates(tree_file):
    t = Tree(tree_file)
    top_rank = defaultdict(dict)
    for node in t.traverse('preorder'):
        if node.is_leaf():
            if node.name.count('_') == 4:
                org,__, _, rank, _ = node.name.split('_')
                rank = int(rank[1:-1])
                if org not in top_rank:
                    top_rank[org]['rank'] = rank
                    top_rank[org]['candidate'] = node.name
                else:
                    if rank < top_rank[org]['rank']:
                        top_rank[org]['rank'] = rank
                        top_rank[org]['candidate'] = node.name
    top_seqs = set()
    for org_ in top_rank.values():
        top_seqs.add(org_['candidate'])
    return top_seqs


def parse_contaminations(file):
    #TODO check contamination file
    cont_dict = {}
    for line in open(file):
        org, tax, rank = line.split('\t')
        cont_dict[org] = (tax, rank.strip())
    return cont_dict


def expected_neighborhood(parent, cont_key_rank):
    keywords = set()
    key = cont_key_rank[0]
    rank = cont_key_rank[1]
    assert rank in ['group', 'subtax', 'org'], f'{rank} has to be group,subtax or org'
    for org in parent.get_leaf_names():
        if (org.count('_') != 4):
            if '..' in org:
                org = org.split('..')[0]
            else:
                org = org.split('_')[0]
            if rank == 'group':
                keywords.add(metadata[org]['group'])
            elif rank == 'subtax':
                keywords.add(metadata[org]['subtax'])
            elif rank == 'org':
                keywords.add(org)
    if keywords:
        if len(keywords) == 1:
            if key in list(keywords)[0]:
                return True
            else:
                return False
        else:
            return False
    return expected_neighborhood(parent.up, cont_key_rank)


def check_contamination(node, cont_dict):
    org = node.name.split('_')[0]
    if expected_neighborhood(node.up, cont_dict[org]):
        return True
    return False


def collect_contaminations(tree_file, cont_dict):
    t = Tree(tree_file)
    R = t.get_midpoint_outgroup()
    t.set_outgroup(R)
    cont_table_name = set()

    contaminations = set()
    n = 0
    for node in t.traverse('preorder'):
        if node.is_leaf() is True:
            if node.name.count('_') == 4:
                name = node.name
                org = name.split('_')[0]
                quality = f'{node.name.split("_")[-3]}_{node.name.split("_")[-2]}_{node.name.split("_")[-1]}'
                table_name = f'{metadata[org]["full"]}_{quality}@{org}'
                if org in cont_dict:
                    if check_contamination(node, cont_dict) is True:
                        contaminations.add(name)
                        cont_table_name.add(table_name)
        n += 1
    return contaminations, cont_table_name


def tree_to_pdf(tree_file, contaminations=None, backpropagion=None):
    if contaminations is None:
        contaminations = []
    tree_base = str(os.path.basename(tree_file))
    if args.prefix:
        tree_base = tree_base.replace(args.prefix, '')
    if args.suffix:
        tree_base = tree_base.replace(args.suffix, '')

    output_base = f"{output_folder}/{tree_base}"
    if not backpropagion:
        table = open(f"{output_folder}/{tree_base}.tsv",'w')

    top_ranked = get_best_candidates(tree_file)
    t = Tree(tree_file)
    ts = TreeStyle()
    R = t.get_midpoint_outgroup()
    t.set_outgroup(R)
    sus_clades = 0

    for node in t.traverse('preorder'):
        node_style = NodeStyle()
        node_style['vt_line_width'] = 3
        node_style['hz_line_width'] = 3
        node_style['vt_line_type'] = 0
        node_style['hz_line_type'] = 0

        if node.is_root() is False:
            if node.is_leaf() is False:
                supp = TextFace(f'{int(node.support)}', fsize=8)
                if node.support >= 70:
                    supp.bold = True
                    taxons = set()
                    taxons_list = []
                    orgs = node.get_leaf_names()
                    if len(orgs) > 1:
                        for org in orgs:
                            if '..' in org:
                                org = org.split('..')[0]
                            else:
                                org = org.split('_')[0]
                            taxons.add(metadata[org]['group'])
                            taxons_list.append(metadata[org]['group'])
                    if len(taxons) > 1 and (len(node) < (len(t)-len(node))):
                        node_style['shape'] = 'sphere'
                        node_style['size'] = 12
                        node_style['fgcolor'] = 'red'
                        node_style['bgcolor'] = 'Silver'
                        sus_clades += 1
                else:
                    supp.fsize = 7
                node.add_face(supp, column=0, position="branch-bottom")
            else:
                empty_face = TextFace("\t"*20)
                node.add_face(empty_face, column=2, position = "aligned")
                node.add_face(empty_face, column=3, position="aligned")
                original_name = node.name
                org = node.name
                if org.count('_') == 4:
                    quality = f'{org.split("_")[-3]}_{org.split("_")[-2]}_{org.split("_")[-1]}'
                    org = original_name.split('_')[0]
                    group = metadata[org]['group']


                    if group in tax_col:
                        tax_name = TextFace(f'[{group} {metadata[org]["subtax"]}]', fgcolor=tax_col[group], bold=True)
                    else:
                        tax_name = TextFace(f'[{group} {metadata[org]["subtax"]}]', bold=True)
                    node.add_face(tax_name, column=1, position = "aligned")

                    if original_name in contaminations:
                        if not backpropagion:
                            table.write(f'{metadata[org]["full"]}_{quality}@{org}\t{group}\td\n')
                        paraf = TextFace(f'{metadata[org]["full"]}_{quality}@{org}', fgcolor='red')
                        node.name = ''
                        node.add_face(paraf, column=0)
                    elif node.name in top_ranked:
                        tname = TextFace(f'{metadata[org]["full"]}_{quality}@{org}', bold=True)
                        if not backpropagion:
                            table.write(f'{metadata[org]["full"]}_{quality}@{org}\t{group}\to\n')
                        node.name = ''
                        node.add_face(tname, column=0, position='branch-right')
                    else:
                        if not backpropagion:
                            table.write(f'{metadata[org]["full"]}_{quality}@{org}\t{group}\tp\n')
                        node.name = f'{metadata[org]["full"]}_{quality}@{org}'


                elif '..' in org:
                    org, length = org.split('_')
                    para = org
                    org = org.split('..')[0]
                    group = f"{metadata[org]['group']}"
                    paraf = TextFace(f'{metadata[org]["full"]}_{length}@{para}', fgcolor='blue')
                    node.name = ''
                    node.add_face(paraf, column=0)
                    if not backpropagion:
                        table.write(f'{metadata[org]["full"]}_{length}@{para}\t{group}\tp\n')
                    gface = TextFace(f'[{group} {metadata[org]["subtax"]}]')
                    node.add_face(gface, column=1, position="aligned")

                else:
                    org, length = org.split('_')
                    group = f"{metadata[org]['group']}"
                    gface = TextFace(f'[{group} {metadata[org]["subtax"]}]') #TODO do not touch me pleeeease
                    color = metadata[org]['col']
                    node_style["bgcolor"] = color
                    if not backpropagion:
                        table.write(f'{metadata[org]["full"]}_{length}@{org}\t{group}\to\n')
                    node.name = f'{metadata[org]["full"]}_{length}@{org}'
                    node.add_face(gface, column=1, position="aligned")
            node.set_style(node_style)

    name_ , trim_len = tree_base.split('_')
    title_face = TextFace(f'<{name_}  trim_aln_len: {trim_len}, {sus_clades} suspicious clades>',  bold=True)
    ts.title.add_face(title_face, column=1)
    t.render(output_base + '_tree.svg', tree_style=ts)
    if not backpropagion:
        table.close()


def trees_plus_table(trees):
    with Pool(processes=threads) as pool:
        suspicious = list(pool.map(suspicious_clades, trees))
        return suspicious


def nonredundant(result_clades):
    nonredundant = []
    for clades in result_clades:
        if clades:
            sorted_clades = sorted(clades, key=lambda clade: len(clade))
            sorted_sets = [set(clade) for clade in sorted_clades]
            for i, set_ in enumerate(sorted_sets):
                redundant = False
                if i < len(sorted_sets):
                    for other in sorted_sets[i+1:]:
                        if set_.issubset(other):
                            redundant = True
                if redundant is False:
                    nonredundant.append(set_)
    return nonredundant


def problematic(nonredundant_clades_):
    problematic_orgs_ = defaultdict(list)
    for clade in nonredundant_clades_:
        taxons = []
        for org in clade:
            if '..' in org:
                org = org.split('..')[0]
            else:
                org = org.split('_')[0]
            taxons.append(metadata[org]["group"])
        group_perc = {}
        for tax in set(taxons):
            group_perc[tax] = (taxons.count(tax)/len(taxons)) * 100
        max_perc = max(group_perc, key=group_perc.get)
        for seq in clade:
            if '..' in seq:
                org = seq.split('..')[0]
            else:
                org = seq.split('_')[0]
            if group_perc[metadata[org]["group"]] == 50:
                problematic_orgs_[org].append('unspecified')
            else:
                problematic_orgs_[org].append(max_perc)
    return problematic_orgs_


def plot_problematic(problematic_orgs):
    max_ = 0
    for org, groups in sorted(problematic_orgs.items()):
        counted_groups = dict(Counter(groups))
        group_total = 0
        for group in counted_groups.values():
            group_total += group
        if group_total > max_:
            max_ = group_total
    with PdfPages('problematic_orgs.pdf') as pdf:
        for org, groups in sorted(problematic_orgs.items()):
            counted_groups = dict(Counter(groups))
            colors = []
            for group in counted_groups.keys():
                if group == 'unspecified':
                    colors.append('black')
                else:
                    colors.append(tax_col.get(group, "white"))
            plt.bar(counted_groups.keys(), counted_groups.values(), color=colors)
            plt.tight_layout()
            plt.ylim(0, max_)
            plt.title(f'{org}({metadata[org]["group"]})')
            plt.xticks(rotation='vertical')
            plt.yticks(fontsize=4)
            pdf.savefig(bbox_inches='tight')
            plt.close()


def backpropagate_contamination(tree_file, cont_names):
    tree_base = str(os.path.basename(tree_file))
    if args.prefix:
        tree_base = tree_base.replace(args.prefix, '')
    if args.suffix:
        tree_base = tree_base.replace(args.suffix, '')

    original_table = open(f"{output_folder}/{tree_base}.tsv", 'r').readlines()
    with open(f"{output_folder}/{tree_base}.tsv", 'w') as res_:
        n = 0
        for line in original_table:
            sline = line.split('\t')
            name = sline[0]
            tax = sline[1]
            status = sline[2].strip()
            if name in cont_names:
                status = 'd'
            n += 1
            res_.write(f'{name}\t{tax}\t{status}\n')


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('config.ini')
    parser = argparse.ArgumentParser(description='some description', usage="blabla")
    parser.add_argument('-t', '--trees_folder', required=True)
    parser.add_argument('-o', '--output_folder', required=True)
    parser.add_argument('-m', '--metadata', required=True)
    parser.add_argument('-n', '--input_metadata')
    parser.add_argument('-c', '--contaminations')
    parser.add_argument('-b', '--backpropagate', action='store_true', help='backpropagate contaminations')
    parser.add_argument('--prefix')
    parser.add_argument('--suffix')
    args = parser.parse_args()
    trees_folder = args.trees_folder
    output_folder = args.output_folder

    if not args.backpropagate:
        os.mkdir(output_folder)

    if args.prefix:
        trees = glob.glob(f"{trees_folder}/{args.prefix}*")
    elif args.suffix:
        trees = glob.glob(f"{trees_folder}/*{args.suffix}")
    else:
        trees = glob.glob(f"{trees_folder}/*")

    number_of_genes = len(trees)
    metadata, tax_col = parse_metadata(args.metadata, args.input_metadata)
    threads = 1 #TODO pararell run

    if not args.backpropagate:
        suspicious = trees_plus_table(trees)
        suspicious = sorted(suspicious)

        with open('suspicious.txt', 'w') as res:
            for file, clades in suspicious:
                if clades:
                    res.write(f'{file}\n========================\n')
                    for clade_ in clades:
                        res.write(f'{clade_}\n')
                    res.write(f'\n\n\n')
        result_clades = [clades[1] for clades in suspicious]
        nonredundant_clades = nonredundant(result_clades)
        problematic_orgs = problematic(nonredundant_clades)
        plot_problematic(problematic_orgs)

    if args.contaminations:
        cont_dict = parse_contaminations(args.contaminations)
        for tree in trees:
            contaminations, contaminated_table = collect_contaminations(tree, cont_dict)
            if args.backpropagate:
               backpropagate_contamination(tree, contaminated_table)
               tree_to_pdf(tree, contaminations, backpropagion=True)
            else:
                tree_to_pdf(tree, contaminations)
    else:
        for tree in trees:
            tree_to_pdf(tree)
