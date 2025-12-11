import scipy.io as sio
p='src/pymgrid/modules/battery/transition_models/data/parameters_cell_NMC.mat'
mat=sio.loadmat(p)
keys=[k for k in mat.keys() if not k.startswith('__')]
print('keys=',keys)
for k in keys:
    v=mat[k]
    try:
        print(k, getattr(v,'shape',None))
    except Exception as e:
        print('err',k,e)
# Try to identify a 2D numeric array
for k in keys:
    v=mat[k]
    if hasattr(v,'shape') and v.ndim==2 and v.shape[1]==6:
        print('Found candidate array',k,v.shape)
        arr=v
        break
else:
    print('No candidate 2D array with 6 columns found')

print('\nSample head 10 rows:')
print(arr[:10])
