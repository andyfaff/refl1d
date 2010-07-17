# Attached please find two data sets for a tethered  approximately 10 nm thick 
# deuterated polystyrene chains in deuterated and hydrogenated toluene. 
# 10 nm thickness is for dry conditions and I am assuming these chains will 
# swell to 14-18 nm thickness once they are in toluene.
#    10ndt is for deuterated toluene case
#    10nht is for hydrogenated toluene case
# I also have to tell you that these chains are bound to the substrate by 
# using an initiator layer between substrate and brush chains. So in your 
# model you should have a silicon layer, silicon oxide layer, initiator layer 
# which is mostly hydrocarbon and scattering length density should be between 
# 0 and 1.5 depending on how much solvent is in the layer. Then you have the 
# swollen brush chains and at the end bulk solvent. When we do these swelling 
# measurements beam penetrate the system from the silicon side and the bottom 
# layer is deuterated or hydrogenated toluene.
import sys
from periodictable import formula
from refl1d import *
from refl1d.fitter import MultiFitProblem
from copy import copy


## =============== Models ======================

## Materials composition based approach.
#deutrated_density = formula("C6H5C2D3").mass/formula("C6H5C2H3").mass
#D_polystyrene = Material("C6H5C2D3", density=0.909*deuterated_density)
#SiOx = Material("SiO2", density=2.634)
#alkane = Material("C8H18",density=0.703)  # Octane formula and density
#deutrated_density = formula("C6H5CD3").mass/formula("C6H5CH3").mass
#H_toluene = Material("C6H5CH3", density=0.8669)
#D_toluene = Material("C6H5CD3", density=0.8669*deuterated_density)
#H_initiator = Compound.byvolume(alkane, H_toluene, 10)
#D_initiator = Compound.byvolume(alkane, D_toluene, H_initiator.fraction[0])



### Deuterated toluene solvent system
D_polystyrene = SLD(name="D-PS",rho=6.2)
SiOx = SLD(name="SiOx",rho=3.47)
D_toluene = SLD(name="D-toluene",rho=5.66)
D_initiator = SLD(name="D-initiator",rho=1.5)
H_toluene = SLD(name="H-toluene",rho=0.94)
H_initiator = SLD(name="H-initiator",rho=0)

D_polymer_layer = TetheredPolymer(polymer=D_polystyrene, solvent=D_toluene,
                                  phi=70, head=120, tail=200, Y=2)

# Stack materials into samples
D = silicon%5 + SiOx/100%5 + D_initiator/100%20 + D_polymer_layer/1000%0 + D_toluene



### Undeuterated toluene solvent system
H_polymer_layer = copy(D_polymer_layer)  # Share tethered polymer parameters...
H_polymer_layer.solvent = H_toluene      # ... but use different solvent
H = silicon + SiOx + H_initiator + H_polymer_layer + H_toluene
for i,_ in enumerate(D):
    H[i].thickness = D[i].thickness
    H[i].interface = D[i].interface

# =============== fitted values ==================

if 0:
    D[0].interface.value = 9

    D[1].interface.value = 30
    D[1].thickness.value = 33
    
    D[2].interface.value = 7
    D_initiator.rho.value = 1.2
    D[2].thickness.value = 0
    
    D_polymer_layer.Y.value = 1.93
    D_polymer_layer.head.value = 64
    D_polymer_layer.phi.value = 64
    D_polystyrene.rho.value = 6.42
    D_polymer_layer.tail.value = 128
    
    H_initiator.rho.value = 0.2


# ================= Fitting parameters ==================

for i in 0, 1, 2:
    D[i].interface.range(0,100)
D[1].thickness.range(0,200)
D[2].thickness.range(0,200)
D_polystyrene.rho.range(6.2,6.5)
SiOx.rho.range(2.07,4.16) # Si - SiO2
#SiOx.rho.pmp(10) # SiOx +/- 10%
D_toluene.rho.pmp(5)
D_initiator.rho.range(0,1.5)
D_polymer_layer.phi.range(50,80)
D_polymer_layer.head.range(0,100)
D_polymer_layer.tail.range(0,500)
D_polymer_layer.Y.range(1.5,2.5)

## Undeuterated system adds two extra parameters
H_toluene.rho.pmp(5)
H_initiator.rho.range(-0.5,0.5)


# ================= Data files ===========================
instrument = ncnrdata.NG7(Qlo=0.005, slits_at_Qlo=0.075)
D_probe = instrument.load('10ndt001.refl', back_reflectivity=True)
H_probe = instrument.load('10nht001.refl', back_reflectivity=True)


# ================== Model variations ====================
dream_opts = dict(chains=20,draws=300000,burn=1000000)
store = "T3" 
if len(sys.argv) > 1: store=sys.argv[1]
if store == "T1":
    dream_opts = dict(chains=20,draws=100000,burn=300000)
    title = "First try; phi=70"
elif store == "T2":
    dream_opts = dict(chains=20,draws=100000,burn=300000)
    title = "fixed SiOx, H/D-toluene rho"
    SiOx.rho.fixed = True
    D_toluene.rho.fixed = True
    H_toluene.rho.fixed = True    
elif store == "T3":
    dream_opts = dict(chains=20,draws=100000,burn=1000000)
    #dream_opts = dict(chains=20,draws=1000,burn=0)
    title = "fixed SiOx, no initiator"
    SiOx.rho.fixed = True
    D_toluene.rho.fixed = True
    H_toluene.rho.fixed = True
    D_polymer_layer.Y.range(1,4)
    del D[2]
    del H[2]
elif store == "T4":
    dream_opts = dict(chains=20,draws=100000,burn=1000000)
    D_polymer_layer.Y.range(1,4)
    title = "free all"
elif store == "T5":
    dream_opts = dict(chains=20,draws=100000,burn=1000000)
    title = "fixed SiOx, initiator w>40"
    SiOx.rho.fixed = True
    D_toluene.rho.fixed = True
    H_toluene.rho.fixed = True
    D[2].thickness.range(40,200)
    D_polymer_layer.Y.range(1,4)
elif store == "T6":
    dream_opts = dict(chains=20,draws=100000,burn=1000000)
    title = "free all, initiator rho in [-1,5]"
    D_polymer_layer.Y.range(1,4)
    D_initiator.rho.range(-1,5)
    H_initiator.rho.range(-1,5)
else:
    raise RuntimeError("store %s not defined"%store)

# Join models and data
D_model = Experiment(sample=D, probe=D_probe)
H_model = Experiment(sample=H, probe=H_probe)
models = D_model, H_model

# Needed by dream fitter
problem = MultiFitProblem(models=models)
problem.dream_opts = dream_opts
problem.name = "tethered"
problem.title = title
problem.store = store
#Probe.view = 'log'