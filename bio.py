import os
from ase import io
from ase.io.cube import read_cube_data
from batoms import Batoms
from time import time

def read(filename, **kwargs):
    """
    wrapper function for ase.io.read
    """
    base = os.path.basename(filename)
    base = os.path.splitext(base)
    label = base[0]
    label = label.replace('-', '_')
    ext = base[1]
    if ext == '.cube':
        # tstart = time()
        volume, atoms = read_cube_data(filename, **kwargs)
        # print('Read cube: {0:1.2f}'.format(time() - tstart))
        batoms = Batoms(label, atoms = atoms, volume=volume)
    else:
        atoms = io.read(filename=filename, **kwargs)
        batoms = Batoms(label = label, atoms = atoms)
    return batoms