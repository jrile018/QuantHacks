#!/usr/bin/env python3
"""16b_write_fds.py - write the FDS files from the checkpoint made by 16_build_fds.py"""
import os
import numpy as np, pandas as pd
BASE = os.environ.get('BP_DATA') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
OUT = os.path.join(BASE, 'fds')
F, C, DOC, L, pk, tmap, CODE_LEGEND = pd.read_pickle(os.path.join(OUT, '_stage.pkl'))
key = pd.DataFrame({'cik': pk.cik, 'date': pk.date.dt.strftime('%Y%m%d').astype(int)})
X = pd.concat([key, pd.DataFrame(F)], axis=1)
MC = pd.concat([key, pd.DataFrame(C)], axis=1)
Y = pd.concat([key, pd.DataFrame(L)], axis=1)
assert X.select_dtypes(exclude=[np.number]).shape[1] == 0, 'non numeric column in matrix'
assert not X.duplicated(['cik', 'date']).any()
X.to_csv(os.path.join(OUT, 'fds_features.csv'), index=False, float_format='%.6g')
MC.to_csv(os.path.join(OUT, 'fds_missing.csv'), index=False)
Y.to_csv(os.path.join(OUT, 'fds_labels.csv'), index=False, float_format='%.6g')
tmap[tmap.cik.isin(pk.cik.unique())].sort_values('cik').to_csv(os.path.join(OUT, 'fds_lookup_cik_ticker.csv'), index=False)
pd.DataFrame([(k, v) for k, v in CODE_LEGEND.items()], columns=['code', 'meaning']).to_csv(os.path.join(OUT, 'fds_lookup_codes.csv'), index=False)
pd.DataFrame([(k, *v) for k, v in DOC.items()], columns=['column', 'block', 'unit', 'description']).to_csv(os.path.join(OUT, 'fds_dictionary.csv'), index=False)
print('done', X.shape, Y.shape, MC.shape)
