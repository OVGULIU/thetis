# Idealised channel flow in 3D
# ============================
#
# Solves hydrostatic flow in a rectangular channel.
#
# Tuomas Karna 2015-03-03

from firedrake import *
import numpy as np
import os
import sys
import time as timeMod
from mpi4py import MPI
from scipy.interpolate import interp1d
import cofs.module_2d as mode2d
import cofs.module_3d as mode3d
from cofs.utility import *
from cofs.physical_constants import physical_constants

# HACK to fix unknown node: XXX / (F0) COFFEE errors
op2.init()
parameters['coffee']['O2'] = False

#parameters['form_compiler']['quadrature_degree'] = 6  # 'auto'
parameters['form_compiler']['optimize'] = False
parameters['form_compiler']['cpp_optimize'] = True
parameters['form_compiler']['cpp_optimize_flags'] = '-O3 -xhost'

#from pyop2 import op2
comm = op2.MPI.comm
commrank = op2.MPI.comm.rank
op2.init(log_level=WARNING)  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# set physical constants
physical_constants['z0_friction'].assign(1.0e-6)
#physical_constants['viscosity_h'].assign(0.0)

mesh2d = Mesh('channel_mesh.msh')

# Function spaces for 2d mode
P1_2d = FunctionSpace(mesh2d, 'CG', 1)
U_2d = VectorFunctionSpace(mesh2d, 'DG', 1)
U_visu_2d = VectorFunctionSpace(mesh2d, 'CG', 1)
U_scalar_2d = FunctionSpace(mesh2d, 'DG', 1)
H_2d = FunctionSpace(mesh2d, 'CG', 2)
W_2d = MixedFunctionSpace([U_2d, H_2d])

solution2d = Function(W_2d, name='solution2d')
# Mean free surface height (bathymetry)
bathymetry2d = Function(P1_2d, name='Bathymetry')

uv_bottom2d = Function(U_2d, name='Bottom Velocity')
z_bottom2d = Function(P1_2d, name='Bot. Vel. z coord')
bottom_drag2d = Function(P1_2d, name='Bottom Drag')

use_wd = False
nonlin = True
swe2d = mode2d.freeSurfaceEquations(mesh2d, W_2d, solution2d, bathymetry2d,
                                    uv_bottom2d, bottom_drag2d,
                                    nonlin=nonlin, use_wd=use_wd)

#bath_x = np.array([0, 10e3, 30e3, 45e3, 100e3])
#bath_v = np.array([20, 20, 6, 15, 5])
depth_oce = 20.0
depth_riv = 5.0
bath_x = np.array([0, 100e3])
bath_v = np.array([depth_oce, depth_riv])
depth = 20.0


def bath(x, y, z):
    padval = 1e20
    x0 = np.hstack(([-padval], bath_x, [padval]))
    vals0 = np.hstack(([bath_v[0]], bath_v, [bath_v[-1]]))
    return interp1d(x0, vals0)(x)

#define a bath func depending on x,y,z
x_func = Function(P1_2d).interpolate(Expression('x[0]'))
bathymetry2d.dat.data[:] = bath(x_func.dat.data, 0, 0)

outputDir = createDirectory('outputs_closed')
bathfile = File(os.path.join(outputDir, 'bath.pvd'))
bathfile << bathymetry2d

elev_x = np.array([0, 30e3, 100e3])
elev_v = np.array([6, 0, 0])


def elevation(x, y, z, x_array, val_array):
    padval = 1e20
    x0 = np.hstack(([-padval], x_array, [padval]))
    vals0 = np.hstack(([val_array[0]], val_array, [val_array[-1]]))
    return interp1d(x0, vals0)(x)

x_func = Function(H_2d).interpolate(Expression('x[0]'))
elev_init = Function(H_2d)
elev_init.dat.data[:] = elevation(x_func.dat.data, 0, 0,
                                  elev_x, elev_v)

# create 3d equations

# extrude mesh
n_layers = 6
mesh = extrudeMeshSigma(mesh2d, n_layers, bathymetry2d)

# function spaces
P1 = FunctionSpace(mesh, 'CG', 1, vfamily='CG', vdegree=1)
U = VectorFunctionSpace(mesh, 'DG', 1, vfamily='CG', vdegree=1)
U_visu = VectorFunctionSpace(mesh, 'CG', 1, vfamily='CG', vdegree=1)
U_scalar = FunctionSpace(mesh, 'DG', 1, vfamily='CG', vdegree=1)
H = FunctionSpace(mesh, 'CG', 2, vfamily='CG', vdegree=1)

eta3d = Function(H, name='Elevation')
eta3d_nplushalf = Function(H, name='Elevation')
bathymetry3d = Function(P1, name='Bathymetry')
copy2dFieldTo3d(swe2d.bathymetry, bathymetry3d)
uv3d = Function(U, name='Velocity')
uv_bottom3d = Function(U, name='Bottom Velocity')
z_bottom3d = Function(P1, name='Bot. Vel. z coord')
# z coordinate in the strecthed mesh
z_coord3d = Function(P1, name='Bot. Vel. z coord')
# z coordinate in the reference mesh (eta=0)
z_coord_ref3d = Function(P1, name='Bot. Vel. z coord')
bottom_drag3d = Function(P1, name='Bottom Drag')
uv3d_dav = Function(U, name='Depth Averaged Velocity')
uv2d_dav = Function(U_2d, name='Depth Averaged Velocity')
uv2d_dav_old = Function(U_2d, name='Depth Averaged Velocity')
w3d = Function(H, name='Vertical Velocity')
w_mesh3d = Function(H, name='Vertical Velocity')
dw_mesh_dz_3d = Function(H, name='Vertical Velocity')
w_mesh_surf3d = Function(H, name='Vertical Velocity')
salt3d = Function(H, name='Salinity')
viscosity_v3d = Function(P1, name='Vertical Velocity')

salt_init3d = Function(H, name='initial salinity')
#salt_init3d.interpolate(Expression('x[0]/1.0e5*10.0+2.0'))
salt_init3d.interpolate(Expression('4.5'))


def getZCoord(zcoord):
    fs = zcoord.function_space()
    tri = TrialFunction(fs)
    test = TestFunction(fs)
    a = tri*test*dx
    L = fs.mesh().coordinates[2]*test*dx
    solve(a == L, zcoord)
    return zcoord

getZCoord(z_coord3d)
z_coord_ref3d.assign(z_coord3d)

mom_eq3d = mode3d.momentumEquation(mesh, U, U_scalar, swe2d.boundary_markers,
                                   swe2d.boundary_len, uv3d, eta3d,
                                   bathymetry3d, w=w3d,
                                   w_mesh=w_mesh3d,
                                   dw_mesh_dz=dw_mesh_dz_3d,
                                   viscosity_v=None,
                                   nonlin=nonlin)
salt_eq3d = mode3d.tracerEquation(mesh, H, salt3d, eta3d, uv3d, w=w3d,
                                  w_mesh=w_mesh3d,
                                  dw_mesh_dz=dw_mesh_dz_3d,
                                  bnd_markers=swe2d.boundary_markers,
                                  bnd_len=swe2d.boundary_len)
vmom_eq3d = mode3d.verticalMomentumEquation(mesh, U, U_scalar, uv3d, w=None,
                                            viscosity_v=viscosity_v3d,
                                            uv_bottom=uv_bottom3d,
                                            bottom_drag=bottom_drag3d)

T = 48 * 3600  # 100*24*3600
Umag = Constant(4.0)
mesh_dt = swe2d.getTimeStepAdvection(Umag=Umag)
dt = float(np.floor(mesh_dt.dat.data.min()/10.0))*0.80
dt = round(comm.allreduce(dt, dt, op=MPI.MIN))
TExport = 100.0
mesh2d_dt = swe2d.getTimeStep(Umag=Umag)
dt_2d = mesh2d_dt.dat.data.min()/20.0
dt_2d = comm.allreduce(dt_2d, dt_2d, op=MPI.MIN)
M_modesplit = int(np.ceil(dt/dt_2d))
dt_2d = float(dt/M_modesplit)
if commrank == 0:
    print 'dt =', dt
    print '2D dt =', dt_2d, M_modesplit
    sys.stdout.flush()

# weak boundary conditions
solution_ext_2d = Function(swe2d.space)
u_ext_2d, h_ext_2d = split(solution_ext_2d)
h_amp = 2.0
flux_amp = -2.0
h_T = 12 * 3600  # 44714.0
uv_river = -0.3
flux_river = 1500*depth_riv*uv_river
t = 0.0
T_ramp = 3600.0
ocean_elev_func = lambda t: h_amp * sin(2 * pi * t / h_T)  # + 3*pi/2)
ocean_elev = Function(swe2d.space.sub(1)).interpolate(Expression(ocean_elev_func(t)))
ocean_elev_3d = Function(H).interpolate(Expression(ocean_elev_func(t)))
ocean_un_func = lambda t: (flux_amp*sin(2 * pi * t / h_T) -
                           uv_river)*min(t/T_ramp, 1.0)
ocean_un = Function(H_2d).interpolate(Expression(ocean_un_func(t)))
ocean_un_3d = Function(H).interpolate(Expression(ocean_un_func(t)))
river_flux_func = lambda t: flux_river*min(t/T_ramp, 1.0)
river_flux = Function(U_scalar_2d).interpolate(Expression(river_flux_func(t)))
river_flux_3d = Function(U_scalar).interpolate(Expression(river_flux_func(t)))
ocean_funcs = {'un': ocean_un}
river_funcs = {'flux': river_flux}
ocean_funcs_3d = {'un': ocean_un_3d}
river_funcs_3d = {'flux': river_flux_3d}
ocean_salt_3d = {'value': salt_init3d}
river_salt_3d = {'value': salt_init3d}
#swe2d.bnd_functions = {2: ocean_funcs, 1: river_funcs}
#mom_eq3d.bnd_functions = {2: ocean_funcs_3d, 1: river_funcs_3d}
#salt_eq3d.bnd_functions = {2: ocean_salt_3d, 1: river_salt_3d}

solver_parameters = {
    #'ksp_type': 'fgmres',
    #'ksp_monitor': True,
    'ksp_rtol': 1e-12,
    'ksp_atol': 1e-16,
    #'pc_type': 'fieldsplit',
    #'pc_fieldsplit_type': 'multiplicative',
}
subIterator = mode2d.SSPRK33(swe2d, dt_2d, solver_parameters)
timeStepper2d = mode2d.macroTimeStepIntegrator(subIterator,
                                               M_modesplit,
                                               restartFromAv=True)

timeStepper_mom3d = mode3d.SSPRK33(mom_eq3d, dt,
                                   funcs_nplushalf={'eta': eta3d_nplushalf})
timeStepper_salt3d = mode3d.SSPRK33(salt_eq3d, dt)
timeStepper_vmom3d = mode3d.CrankNicolson(vmom_eq3d, dt, gamma=0.6)

U_2d_file = exporter(U_visu_2d, 'Depth averaged velocity', outputDir, 'Velocity2d.pvd')
eta_2d_file = exporter(P1_2d, 'Elevation', outputDir, 'Elevation2d.pvd')
eta_3d_file = exporter(P1, 'Elevation', outputDir, 'Elevation3d.pvd')
uv_3d_file = exporter(U_visu, 'Velocity', outputDir, 'Velocity3d.pvd')
w_3d_file = exporter(P1, 'V.Velocity', outputDir, 'VertVelo3d.pvd')
w_mesh_3d_file = exporter(P1, 'Mesh Velocity', outputDir, 'MeshVelo3d.pvd')
salt_3d_file = exporter(P1, 'Salinity', outputDir, 'Salinity3d.pvd')
uv_dav_2d_file = exporter(U_visu_2d, 'Depth Averaged Velocity', outputDir, 'DAVelocity2d.pvd')
uv_bot_2d_file = exporter(U_visu_2d, 'Bottom Velocity', outputDir, 'BotVelocity2d.pvd')
visc_3d_file = exporter(P1, 'Vertical Viscosity', outputDir, 'Viscosity3d.pvd')

# assign initial conditions
uv2d, eta2d = solution2d.split()
eta2d.assign(elev_init)
copy2dFieldTo3d(elev_init, eta3d)
#getZCoord(z_coord3d)
updateCoordinates(mesh, eta3d, bathymetry3d, z_coord3d, z_coord_ref3d)
salt3d.assign(salt_init3d)
computeVertVelocity(w3d, uv3d, bathymetry3d)  # at t{n+1}
computeMeshVelocity(eta3d, uv3d, w3d, w_mesh3d, w_mesh_surf3d,
                    dw_mesh_dz_3d, bathymetry3d, z_coord_ref3d)
#computeBottomFriction()

timeStepper2d.initialize(solution2d)
timeStepper_mom3d.initialize(uv3d)
timeStepper_salt3d.initialize(salt3d)
timeStepper_vmom3d.initialize(uv3d)

# Export initial conditions
U_2d_file.export(solution2d.split()[0])
eta_2d_file.export(solution2d.split()[1])
eta_3d_file.export(eta3d)
uv_3d_file.export(uv3d)
w_3d_file.export(w3d)
w_mesh_3d_file.export(w_mesh3d)
salt_3d_file.export(salt3d)
uv_dav_2d_file.export(uv2d_dav)
uv_bot_2d_file.export(uv_bottom2d)
visc_3d_file.export(viscosity_v3d)

# The time-stepping loop
T_epsilon = 1.0e-5
cputimestamp = timeMod.clock()
t = 0
i = 0
iExp = 1
next_export_t = t + TExport


def updateForcings(t_new):
    ocean_elev.dat.data[:] = ocean_elev_func(t_new)
    ocean_un.dat.data[:] = ocean_un_func(t_new)
    river_flux.dat.data[:] = river_flux_func(t_new)


def updateForcings3d(t_new):
    ocean_elev_3d.dat.data[:] = ocean_elev_func(t_new)
    ocean_un_3d.dat.data[:] = ocean_un_func(t_new)
    river_flux_3d.dat.data[:] = river_flux_func(t_new)


def computeBottomFriction():
    copy3dFieldTo2d(uv3d, uv_bottom2d, level=-2)
    copy2dFieldTo3d(uv_bottom2d, uv_bottom3d)
    copy3dFieldTo2d(z_coord3d, z_bottom2d, level=-2)
    copy2dFieldTo3d(z_bottom2d, z_bottom3d)
    z_bottom2d.dat.data[:] += bathymetry2d.dat.data[:]
    computeBottomDrag(uv_bottom2d, z_bottom2d, bathymetry2d, bottom_drag2d)
    copy2dFieldTo3d(bottom_drag2d, bottom_drag3d)


def compVolume(eta):
    val = assemble(eta * swe2d.dx)
    return op2.MPI.COMM.allreduce(val, op=MPI.SUM)


def compVolume3d():
    one = Constant(1.0)
    val = assemble(one*dx)
    return op2.MPI.COMM.allreduce(val, op=MPI.SUM)


def compTracerMass3d(scalarFunc):
    val = assemble(scalarFunc*dx)
    return op2.MPI.COMM.allreduce(val, op=MPI.SUM)

Vol_0 = compVolume(eta2d)
Vol3d_0 = compVolume3d()
Mass3d_0 = compTracerMass3d(salt3d)
print 'Initial volume', Vol_0, Vol3d_0

from pyop2.profiling import timed_region, timed_function, timing

while t <= T + T_epsilon:

    # For DIRK3 2d time integrator
    #print('solving 2d mode')
    #timeStepper2d.advance(t, dt, swe2d.solution, updateForcings)
    #print('preparing 3d fields')
    #copy2dFieldTo3d(swe2d.solution.split()[1], eta3d)
    #print('solving 3d mode')
    #timeStepper_mom3d.advance(t, dt, uv3d, updateForcings3d)
    #print('solving 3d continuity')
    #computeVertVelocity(w3d, uv3d, bathymetry3d)
    #print('solving 3d tracers')
    #timeStepper_salt3d.advance(t, dt, salt3d, None)

    # SSPRK33 time integration loop
    with timed_region('mode2d'):
        #timeStepper2d.advance(t-dt/2, dt, swe2d.solution, updateForcings)
        timeStepper2d.advance(t, dt_2d, solution2d, updateForcings)
    with timed_region('aux_functions'):
        eta_n = solution2d.split()[1]
        copy2dFieldTo3d(eta_n, eta3d)  # at t_{n+1}
        eta_nph = timeStepper2d.solution_nplushalf.split()[1]
        copy2dFieldTo3d(eta_nph, eta3d_nplushalf)  # at t_{n+1/2}
        updateCoordinates(mesh, eta3d, bathymetry3d, z_coord3d, z_coord_ref3d)
        computeBottomFriction()
    with timed_region('momentumEq'):
        timeStepper_mom3d.advance(t, dt, uv3d, updateForcings3d)
    with timed_region('aux_functions'):
        computeParabolicViscosity(uv_bottom3d, bottom_drag3d, bathymetry3d,
                                  viscosity_v3d)
    with timed_region('vert_diffusion'):
        timeStepper_vmom3d.advance(t, dt, uv3d, None)
    with timed_region('continuityEq'):
        computeVertVelocity(w3d, uv3d, bathymetry3d)  # at t{n+1}
        computeMeshVelocity(eta3d, uv3d, w3d, w_mesh3d, w_mesh_surf3d,
                            dw_mesh_dz_3d, bathymetry3d, z_coord_ref3d)
        #dw_mesh_dz_3d.assign(0.0)
        #w_mesh3d.assign(0.0)
        computeBottomFriction()
    with timed_region('saltEq'):
        timeStepper_salt3d.advance(t, dt, salt3d, updateForcings3d)
    with timed_region('aux_functions'):
        bndValue = Constant((0.0, 0.0, 0.0))
        computeVerticalIntegral(uv3d, uv3d_dav, U,
                                bottomToTop=True, bndValue=bndValue,
                                average=True, bathymetry=bathymetry3d)
        copy3dFieldTo2d(uv3d_dav, uv2d_dav, useBottomValue=False)
        # 2d-3d coupling: restart 2d mode from depth ave 3d velocity
        timeStepper2d.solution_start.split()[0].assign(uv2d_dav)
    #with timed_region('continuityEq'):
        #computeVertVelocity(w3d, uv3d, bathymetry3d)  # at t{n+1}

    # Move to next time step
    t += dt
    i += 1

    ## LF-AM3 time integration loop
    #with timed_region('aux_functions'):
        #eta_n = swe2d.solution.split()[1]
        #copy2dFieldTo3d(eta_n, eta3d)  # at t_{n}
        #computeBottomFriction()
    ## prediction step, update 3d fields from t_{n-1/2} to t_{n+1/2}
    #with timed_region('saltEq'):
        #timeStepper_salt3d.predict(t, dt, salt3d, updateForcings3d)
    #with timed_region('momentumEq'):
        #timeStepper_mom3d.predict(t, dt, uv3d, None)
    #with timed_region('continuityEq'):
        #computeVertVelocity(w3d, uv3d, bathymetry3d)
    #with timed_region('mode2d'):
        #timeStepper2d.advance(t, dt, swe2d.solution, updateForcings)
        ##timeStepper2d.advanceMacroStep(t, dt_2d, M_modesplit,
                                       ##swe2d.solution, updateForcings)
    #with timed_region('aux_functions'):
        #eta_nplushalf = timeStepper2d.solution_nplushalf.split()[1]
        #copy2dFieldTo3d(eta_nplushalf, eta3d)  # at t_{n+1/2}
        #computeBottomFriction()
        #computeParabolicViscosity(uv_bottom3d, bottom_drag3d, bathymetry3d, 
                                  #viscosity_v3d)
    #with timed_region('saltEq'):
        #timeStepper_salt3d.correct(t, dt, salt3d, updateForcings3d)  # at t{n+1}
    #with timed_region('momentumEq'):
        #timeStepper_mom3d.correct(t, dt, uv3d, None)  # at t{n+1}
    #with timed_region('vert_diffusion'):
        #timeStepper_vmom3d.advance(t, dt, uv3d, None)
    #with timed_region('aux_functions'):
        #UV_n = swe2d.solution.split()[0]
        #bndValue = Constant((0.0, 0.0, 0.0))
        #computeVerticalIntegral(uv3d, uv3d_dav, U,
                                #bottomToTop=True, bndValue=bndValue,
                                #average=True, bathymetry=bathymetry3d)
        #copy3dFieldTo2d(uv3d_dav, uv2d_dav, useBottomValue=False)
        #UV_n.assign(uv2d_dav)
    #with timed_region('continuityEq'):
        #computeVertVelocity(w3d, uv3d, bathymetry3d)  # at t{n+1}

    # Write the solution to file
    if t >= next_export_t - T_epsilon:
        cputime = timeMod.clock() - cputimestamp
        cputimestamp = timeMod.clock()
        norm_h = norm(solution2d.split()[1])
        norm_u = norm(solution2d.split()[0])

        if commrank == 0:
            line = ('{iexp:5d} {i:5d} T={t:10.2f} '
                    'eta norm: {e:10.4f} u norm: {u:10.4f} {cpu:5.2f}')
            print(line.format(iexp=iExp, i=i, t=t, e=norm_h,
                              u=norm_u, cpu=cputime))
            line = 'Rel. {0:s} error {1:11.4e}'
            print(line.format('vol  ', (Vol_0 - compVolume(solution2d.split()[1]))/Vol_0))
            print(line.format('vol3d', (Vol3d_0 - compVolume3d())/Vol3d_0))
            print(line.format('mass ', (Mass3d_0 - compTracerMass3d(salt3d))/Mass3d_0))
            print 'salt ', salt3d.dat.data.min()-4.5, salt3d.dat.data.max()-4.5

            sys.stdout.flush()
        U_2d_file.export(solution2d.split()[0])
        eta_2d_file.export(solution2d.split()[1])
        eta_3d_file.export(eta3d)
        uv_3d_file.export(uv3d)
        w_3d_file.export(w3d)
        w_mesh_3d_file.export(w_mesh3d)
        salt_3d_file.export(salt3d)
        uv_dav_2d_file.export(uv2d_dav)
        uv_bot_2d_file.export(uv_bottom2d)
        visc_3d_file.export(viscosity_v3d)

        next_export_t += TExport
        iExp += 1

        #if commrank == 0:
            #labels = ['mode2d', 'momentumEq', 'vert_diffusion',
                      #'continuityEq', 'saltEq', 'aux_functions']
            #cost = {}
            #relcost = {}
            #totcost = 0
            #for label in labels:
                #value = timing(label, reset=True)
                #cost[label] = value
                #totcost += value
            #for label in labels:
                #c = cost[label]
                #relcost = c/totcost
                #print '{0:25s} : {1:11.6f} {2:11.2f}'.format(label, c, relcost)
                #sys.stdout.flush()