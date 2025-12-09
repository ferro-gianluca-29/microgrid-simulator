#!/usr/bin/env python3
"""Test reading NMC SOH vs Ah throughput curve."""

import pandas as pd

excel_file = r'src/pymgrid/modules/battery/transition_models/data/NMC-SOHAh.xlsx'
df = pd.read_excel(excel_file)

print('Excel file structure:')
print(f'Shape: {df.shape}')
print(f'Columns: {df.columns.tolist()}')
print(f'\nFirst 10 rows:')
print(df.head(10))
print(f'\nLast 5 rows:')
print(df.tail(5))
print(f'\nData types:\n{df.dtypes}')
