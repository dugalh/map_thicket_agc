"""
    GEF5-SLM: Above ground carbon estimation in thicket using multi-spectral images
    Copyright (C) 2020 Dugal Harris
    Email: dugalh@gmail.com

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import matplotlib
matplotlib.use("TkAgg")
matplotlib.interactive(True)

from builtins import zip
from matplotlib import pyplot
import numpy as np
import pathlib, sys, os
from csv import DictWriter
import pandas as pd
from scipy.stats import gaussian_kde
import logging
from agc_estimation import allometry as allom
from agc_estimation import visualisation as vis

if '__file__' in globals():
    root_path = pathlib.Path(__file__).absolute().parents[1]
else:
    root_path = pathlib.Path(os.getcwd())

sys.path.append(str(root_path.joinpath('agc_estimation')))
logging.basicConfig(format='%(levelname)s %(name)s: %(message)s')

model_file_name = root_path.joinpath('data/sampling_inputs/allometry/allometric_models.xlsx')
litter_file_name = root_path.joinpath('data/sampling_inputs/allometry/litter_allometric_data.xlsx')
woody_file_name = root_path.joinpath('data/sampling_inputs/allometry/woody_allometric_data.xlsx')

plant_abc_file_name = root_path.joinpath('data/outputs/allometry/plant_abc_v3.csv')
plot_agc_file_name = root_path.joinpath('data/outputs/allometry/plot_agc_v3.csv')
surrogate_file_name = root_path.joinpath('data/outputs/allometry/master_surrogate_map_v3.csv')

agc_plot_est = allom.AgcPlotEstimator(model_file_name=model_file_name, correction_method=allom.BiomassCorrectionMethod.NicklessZou)
agc_plot_est.estimate(woody_file_name=woody_file_name, litter_file_name=litter_file_name)

if True:
    # write per-plant and per-plot ABC/AGC etc files
    agc_plot_est.write_abc_plant_file(out_file_name=plant_abc_file_name)
    agc_plot_est.write_agc_plot_file(out_file_name=plot_agc_file_name)

    # write out surrogate map
    with open(surrogate_file_name, 'w', newline='') as outfile:
        writer = DictWriter(outfile, list(agc_plot_est._abc_aggregator.master_surrogate_dict.values())[100].keys())
        writer.writeheader()
        writer.writerows(list(agc_plot_est._abc_aggregator.master_surrogate_dict.values()))

    # plot relationships between plant volume and C stocks
    f1 = pyplot.figure('Relation between plant vol. and C stocks')
    f1.set_size_inches(10, 4, forward=True)
    ax = pyplot.subplot(1, 2, 1, aspect='equal')
    vis.scatter_ds(agc_plot_est.plot_summary_agc_df, x_col='VolHa', y_col='AbcHa', xfn=lambda x: x / 1000., yfn=lambda y: y / 1000.,
                   x_label='Biomass volume ($10^3$ m$^{3}$ ha$^{-1}$)', y_label='ABC (t C ha$^{-1}$)')
    ax.set_title('(a)')

    ax = pyplot.subplot(1, 2, 2, aspect='equal')
    vis.scatter_ds(agc_plot_est.plot_summary_agc_df, x_col='VolHa', y_col='AgcHa', xfn=lambda x: x / 1000., yfn=lambda y: y / 1000.,
                   x_label='Biomass volume ($10^3$ m$^{3}$ ha$^{-1}$)', y_label='AGC (t C ha$^{-1}$)')
    ax.set_title('(b)')
    f1.tight_layout()
    f1.waitforbuttonpress(.2)
    f1.savefig(root_path.joinpath('data/outputs/plots/vol_vs_agc_scatter.png'), dpi=300)

    f2 = pyplot.figure('Relation between Litter C and ABC')
    f2.set_size_inches(5, 4, forward=True)
    vis.scatter_ds(agc_plot_est.plot_summary_agc_df, x_col='VolHa', y_col='AgcHa', xfn=lambda x: x / 1000., yfn=lambda y: y / 1000.,
                   x_label='Litter C (t C ha$^{-1}$)', y_label='ABC (t C ha$^{-1}$)')
    f2.tight_layout()
    f2.waitforbuttonpress(.2)
    f2.savefig(root_path.joinpath('data/outputs/plots/litter_c_vs_abc_scatter.png'), dpi=300)


if True:
    # ------------------------------------------------------------------------------------------------------------------
    # Further data analysis (species ABC contributions, per-stratum, plant height ABC contributions, ...)
    plant_abc_df = pd.read_csv(plant_abc_file_name)
    nested_plot_size = 5.

    # make dataframe of per-plot per-species ABC contributions
    plot_species_abc_dict = {}
    for id, id_group in plant_abc_df.groupby('ID'):
        containing_plot_size = float(id_group['plot_size'].max())
        is_nested = np.any(id_group['plot_size'] == nested_plot_size)
        degr_class = id_group['degr_class'].iloc[0].strip()
        plot_species_abc_dict[id] = {'degr_class':degr_class, 'plot_size':containing_plot_size}

        for species, species_group in id_group.groupby('species'):
            nested_idx = species_group['plot_size'] == nested_plot_size
            height_idx = species_group['height'] < 50
            nested_scale_f = (containing_plot_size / nested_plot_size) ** 2
            species_abc = 0
            species_abc += (nested_scale_f * species_group.loc[nested_idx & height_idx, 'yc'].sum()) + species_group.loc[nested_idx & ~height_idx, 'yc'].sum()
            species_abc += species_group.loc[~nested_idx, 'yc'].sum()
            species_abc_ha = species_abc * (100 ** 2) / (containing_plot_size ** 2)
            plot_species_abc_dict[id][species] = species_abc

    plot_species_abc_df = pd.DataFrame(list(plot_species_abc_dict.values()), index=list(plot_species_abc_dict.keys()))
    plot_species_abc_df['ID'] = plot_species_abc_df.index
    plot_species_abc_df = plot_species_abc_df.fillna(value=0)

    # ------------------------------------------------------------------------------------------------------------------
    # Plot 10 highest contributing species (to ABC) per stratum
    degr_species_abc_df = pd.DataFrame()
    overall_degr_species_abc_df = pd.DataFrame()
    overall_plot_area_ttl = np.array([ps ** 2 for ps in plot_species_abc_df['plot_size']]).sum()

    f1 = pyplot.figure('Species contribution to ABC per stratum')
    f1.set_size_inches(10, 4, forward=True)
    plot_idxs = [1, 3, 2]
    for (degr_class, degr_group), plotIdx in zip(plot_species_abc_df.groupby('degr_class', sort=False), plot_idxs):
        species_keys = degr_group.keys().drop(['degr_class', 'plot_size', 'ID'])
        species_abc_ttl = degr_group[species_keys].sum()
        plot_area_ttl = np.array([ps**2 for ps in degr_group['plot_size']]).sum()
        species_abc_ha = (100 ** 2) * species_abc_ttl / (1000 * plot_area_ttl)      # tC/ha

        degr_row = dict(list(zip(species_keys, species_abc_ha)))
        degr_row['degr_class'] = degr_class
        degr_species_abc_df = degr_species_abc_df.append(degr_row, ignore_index=True)

        print('Average ABC in {0} stratum: {1:.3f} tC/ha'.format(degr_class, species_abc_ha.sum()))
        idx = np.argsort(-species_abc_ha)
        pyplot.subplot(1, 3, plotIdx)
        pyplot.bar(np.arange(0, 10), species_abc_ha[idx[:10]], label=degr_class)
        pyplot.xticks(np.arange(0, 10), species_keys[idx[:10]], rotation='vertical')  # prop={'size':fontSize-2})
        pyplot.title(degr_class)
        pyplot.ylabel('t C ha$^{-1}$')
        pyplot.tight_layout()

    f1.waitforbuttonpress(0.2)
    f1.savefig(root_path.joinpath('data/outputs/plots/species_abc_per_stratum.png'), dpi=300)
    degr_species_abc_df.to_excel(root_path.joinpath('data/outputs/allometry/species_abc_contributions_per_stratum.xlsx'))

    # ------------------------------------------------------------------------------------------------------------------
    # Plot plant height probability per stratum
    def plot_plant_heights_kde(plant_heights):
        kde = gaussian_kde(plant_heights)  # , bw_method=bandwidth / height.std(ddof=1))
        height_grid = np.linspace(0, 500, 200)
        height_kde = kde.evaluate(height_grid)
        pyplot.plot(height_grid, height_kde)
        ax_lim = pyplot.axis()
        h = pyplot.plot([50, 50], [0, height_kde.max()], 'r')
        pyplot.xlabel('Plant Height (cm)')
        pyplot.ylabel('Probability')

    plant_abc_df.loc[plant_abc_df['degr_class'] == 'Degraded ', 'degr_class'] = 'Degraded'
    nested_idx = plant_abc_df['plot_size'] == 5
    plant_heights = plant_abc_df.loc[nested_idx, 'height']

    f = pyplot.figure('Plant height distribution by stratum')
    pyplot.subplot(2,2,4)
    plot_plant_heights_kde(plant_heights)
    pyplot.title('Overall')

    plot_idxs = [1, 3, 2]
    for (degr_class, degr_group), plot_idx in zip(plant_abc_df.groupby('degr_class'), plot_idxs):
        nested_idx = degr_group['plot_size'] == 5
        plant_heights = degr_group.loc[nested_idx, 'height']

        pyplot.subplot(2, 2, plot_idx)
        plot_plant_heights_kde(plant_heights)
        pyplot.title(degr_class)
        pyplot.tight_layout()

    f.waitforbuttonpress(0.2)
    f.savefig(root_path.joinpath('data/outputs/plots/plant_height_distribution_by_stratum.png'), dpi=300)

    # ------------------------------------------------------------------------------------------------------------------
    # Plot plant height contribution to ABC per stratum
    def plot_plant_height_abc_contr(abc_df):
        abc_df = abc_df.sort_values(by='height')
        abc_cum_sum = np.cumsum(abc_df['yc'])
        pyplot.plot(abc_df['height'], (100 * abc_cum_sum) / abc_cum_sum.max())
        ax_lim = pyplot.axis()
        h = pyplot.plot([50, 50], [ax_lim[2], ax_lim[3]], 'r')
        pyplot.axis(ax_lim)
        pyplot.grid('on')
        pyplot.xlabel('Plant Height (cm)')
        pyplot.ylabel('% of ABC')

    nested_abc_df = plant_abc_df.loc[plant_abc_df['plot_size'] == 5]

    f = pyplot.figure('Plant height contribution to ABC by stratum')
    pyplot.subplot(2, 2, 4)
    plot_plant_height_abc_contr(nested_abc_df)
    pyplot.title('Overall')

    plot_idxs = [1, 3, 2]
    for (degr_class, degr_group), plotIdx in zip(nested_abc_df.groupby('degr_class'), plot_idxs):
        degr_group = degr_group.sort_values(by='height')
        pyplot.subplot(2, 2, plotIdx)
        plot_plant_height_abc_contr(degr_group)
        pyplot.title(degr_class)
        pyplot.tight_layout()

    f.waitforbuttonpress(.2)    # wait before closing all windows
    f.savefig(root_path.joinpath('data/outputs/plots/plant_height_contribution_to_abc_by_stratum.png'), dpi=300)

# TODO  - we can simulate what the "error" is when we increase the height cutoff idx (exclude heights less than x in
#  containing plot, and extrap heights < x from nested plot, then compare to x=50)
