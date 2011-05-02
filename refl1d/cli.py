from __future__ import with_statement

from math import ceil

import sys
import os

import shutil
import subprocess
try:
    import dill as pickle
except:
    import cPickle as pickle

import numpy

from .stajconvert import load_mlayer, fit_all
from . import fitters
from .fitters import FIT_OPTIONS, FitDriver, StepMonitor, ConsoleMonitor
from .fitproblem import FitProblem, load_problem as load_script
from .mapper import MPMapper, AMQPMapper, SerialMapper
from . import util
from .mystic import parameter
from . import initpop
from . import __version__

from .util import pushdir

# TODO: separate refl specific parameters from generic fitter parameters
from .probe import Probe



def mesh(problem, vars=None, n=40):
    x,y = [numpy.linspace(p.bounds.limits[0],p.bounds.limits[1],n) for p in vars]
    p1, p2 = vars
    def fn(xi,yi):
        p1.value, p2.value = xi,yi
        problem.model_update()
        #parameter.summarize(problem.parameters)
        return problem.chisq()
    z = [[fn(xi,yi) for xi in x] for yi in y]
    return x,y,numpy.asarray(z)

# ===== Model manipulation ====

def load_problem(args):
    path, options = args[0], args[1:]

    directory,filename = os.path.split(path)
    with pushdir(directory):
        if (filename.endswith('.so') or filename.endswith('.dll')
            or filename.endswith('.dyld')):
            from . import garefl
            options = []
            problem = garefl.load(filename)
        elif filename.endswith('.staj'):
            options = []
            problem = FitProblem(load_mlayer(filename))
        elif filename.endswith('.pickle'):
            problem = pickle.load(filename)
        else:
            options = args[1:]
            problem = load_script(filename, options=options)
            # Guard against the user changing parameters after defining
            # the problem.
            problem.model_reset()

    problem.file = path
    if not hasattr(problem,'title'):
        problem.title = filename
    problem.name, _ = os.path.splitext(filename)
    problem.options = options
    return problem

def preview(problem):
    import pylab
    problem.show()
    problem.plot()
    pylab.show()

def remember_best(fitter, problem, best):
    pardata = "".join("%s %.15g\n"%(p.name, p.value)
                      for p in problem.parameters)
    open(problem.output_path+".par",'wt').write(pardata)

    problem.save(problem.output_path)
    with util.redirect_console(problem.output_path+".out"):
        fitter.show()
    fitter.show()
    fitter.plot(problem.output_path)


def recall_best(problem, path):
    data = open(path,'rt').readlines()
    for par,line in zip(problem.parameters, data):
        par.value = float(line.split()[-1])

def store_overwrite_query_gui(path):
    import wx
    msg_dlg = wx.MessageDialog(None,path+" Already exists. Press 'yes' to overwrite, or 'No' to abort and restart with newpath",'Overwrite Directory',wx.YES_NO | wx.ICON_QUESTION)
    retCode = msg_dlg.ShowModal()
    msg_dlg.Destroy()
    if retCode != wx.ID_YES:
        raise RuntimeError("Could not create path")

def store_overwrite_query(path):
    print path,"already exists."
    print "Press 'y' to overwrite, or 'n' to abort and restart with --store=newpath"
    ans = raw_input("Overwrite [y/n]? ")
    if ans not in ("y","Y","yes"):
        sys.exit(1)

def make_store(problem, opts, exists_handler):
    # Determine if command line override
    if opts.store != None:
        problem.store = opts.store
    problem.output_path = os.path.join(problem.store,problem.name)

    # Check if already exists
    if not opts.overwrite and os.path.exists(problem.output_path+'.out'):
        if opts.batch:
            print >>sys.stderr, problem.store+" already exists.  Use --overwrite to replace."
            sys.exit(1)
        exists_handler(problem.output_path)

    # Create it and copy model
    try: os.mkdir(problem.store)
    except: pass
    shutil.copy2(problem.file, problem.store)

    # Redirect sys.stdout to capture progress
    if opts.batch:
        sys.stdout = open(problem.output_path+".mon","w")


def run_profile(problem, steps):
    """
    Model execution time profiler.

    Run the program with "--profile --steps=N" to generate a function
    profile chart breaking down the cost of evaluating N models.

    Here is the findings from one profiling session::

       23 ms total
        6 ms rendering model
        8 ms abeles
        4 ms convolution
        1 ms setting parameters and computing nllf

    Using the GPU for abeles/convolution will only give us 2-3x speedup.
    """
    from .util import profile
    p = initpop.random(N=steps, pars=problem.parameters)

    # The cost of
    # To get good information from the profiler, you wil
    # Modify this function to obtain different information

    # For gathering stats on just the rendering.
    fits = getattr(problem,'fits',[problem])
    def rendering(p):
        problem.setp(p)
        for f in fits:
            f.fitness._render_slabs()

    #profile(map,rendering,p)
    profile(map,problem.nllf,p)
    #map(problem.nllf,p)


def start_remote_fit(problem, options, queue, notify):
    """
    Queue remote fit.
    """
    from jobqueue.client import connect

    data = dict(package='refl1d',
                version=__version__,
                problem=pickle.dumps(problem),
                options=pickle.dumps(options))
    request = dict(service='fitter',
                   version=__version__, # fitter service version
                   notify=notify,
                   name=problem.title,
                   data=data)

    server = connect(queue)
    job = server.submit(request)
    return job


# ==== option parser ====

class ParseOpts:
    MINARGS = 0
    FLAGS = set()
    VALUES = set()
    USAGE = ""
    def __init__(self, args):
        self._parse(args)

    def _parse(self, args):
        flagargs = [v for v in sys.argv[1:] if v.startswith('--') and not '=' in v]
        flags = set(v[2:] for v in flagargs)
        if 'help' in flags or '-h' in sys.argv[1:] or '-?' in sys.argv[1:]:
            print self.USAGE
            sys.exit()
        unknown = flags - self.FLAGS
        if any(unknown):
            raise ValueError("Unknown options --%s.  Use -? for help."%", --".join(unknown))
        for f in self.FLAGS:
            setattr(self, f, (f in flags))

        valueargs = [v for v in sys.argv[1:] if v.startswith('--') and '=' in v]
        for f in valueargs:
            idx = f.find('=')
            name = f[2:idx]
            value = f[idx+1:]
            if name not in self.VALUES:
                raise ValueError("Unknown option --%s. Use -? for help."%name)
            setattr(self, name, value)

        positionargs = [v for v in sys.argv[1:] if not v.startswith('-')]
        self.args = positionargs



class Refl1dOpts(ParseOpts):
    MINARGS = 1
    FLAGS = set(("preview", "check", "profile", "random", "simulate",
                 "worker", "batch", "overwrite", "parallel", "stepmon",
                 "cov", "remote", "staj",
                 "multiprocessing-fork", # passed in when app is a frozen image
               ))
    VALUES = set(("plot", "store", "fit", "noise", "seed", "pars",
                  "resynth", "transport", "notify", "queue",
                  #"mesh","meshsteps",
                ))
    # Add in parameters from the fitters
    VALUES |= set(fitters.FitOptions.FIELDS.keys())
    pars=None
    notify=""
    queue="http://reflectometry.org/queue"
    resynth="0"
    noise="5"
    starts="1"
    seed=""
    PLOTTERS="fresnel", "linear", "log", "q4", "residuals"
    USAGE = """\
Usage: refl1d modelfile [modelargs] [options]

The modelfile is a Python script (i.e., a series of Python commands)
which sets up the data, the models, and the fittable parameters.
The model arguments are available in the modelfile as sys.argv[1:].
Model arguments may not start with '-'.

Options:

    --preview
        display model but do not perform a fitting operation
    --pars=filename
        initial parameter values; fit results are saved as <modelname>.par
    --plot=log      [%(plotter)s]
        type of reflectivity plot to display
    --random
        use a random initial configuration
    --simulate
        simulate the data to fit
    --noise=5%%
        percent noise to add to the simulated data
    --cov
        compute the covariance matrix for the model when done
    --staj
        output staj file when done

    --store=path
        output directory for plots and models
    --overwrite
        if store already exists, replace it
    --parallel
        run fit using all processors
    --batch
        batch mode; don't show plots after fit
    --remote
        queue fit to run on remote server
    --notify=user@email OR @twitterid
        remote fit notification (twitter users must follow @reflfit)
    --queue=http://reflectometry.org
        remote job queue

    --fit=de        [%(fitter)s]
        fitting engine to use; see manual for details
    --steps=1000    [%(fitter)s]
        number of fit iterations after any burn-in time
    --pop=10        [dream, de, rl, ps]
        population size
    --burn=0        [dream, pt]
        number of burn-in iterations before accumulating stats
    --nT=25
    --Tmin=0.1
    --Tmax=10       [pt]
        temperatures vector; use a higher maximum temperature and a larger
        nT if your fit is getting stuck in local minima
    --CR=0.9        [de, rl, pt]
        crossover ratio for population mixing
    --starts=1      [%(fitter)s]
        number of times to run the fit from random starting points
    --init=lhs      [dream]
        population initialization method:
          lhs:    latin hypercube sampling
          cov:    normally distributed according to covariance matrix
          random: uniformly distributed within parameter ranges
    --stepmon
        show details for each step
    --resynth=0
        run resynthesis error analysis for n generations

    --check
        print the model description and chisq value and exit
    -?/-h/--help
        display this help
"""%{'fitter':'|'.join(sorted(FIT_OPTIONS.keys())),
     'plotter':'|'.join(PLOTTERS),
     }

#    --transport=mp  {amqp|mp|mpi}
#        use amqp/multiprocessing/mpi for parallel evaluation
#    --mesh=var OR var+var
#        plot chisq line or plane
#    --meshsteps=n
#        number of steps in the mesh
#For mesh plots, var can be a fitting parameter with optional
#range specifier, such as:
#
#   P[0].range(3,6)
#
#or the complete path to a model parameter:
#
#   M[0].sample[1].material.rho.pm(1)

    _plot = 'log'
    def _set_plot(self, value):
        if value not in set(self.PLOTTERS):
            raise ValueError("unknown plot type %s; use %s"
                             %(value,"|".join(self.PLOTTERS)))
        self._plot = value
    plot = property(fget=lambda self: self._plot, fset=_set_plot)
    store = None
    _fitter = fitters.FIT_DEFAULT
    def _set_fitter(self, value):
        if value not in set(FIT_OPTIONS.keys()):
            raise ValueError("unknown fitter %s; use %s"
                             %(value,"|".join(sorted(FIT_OPTIONS.keys()))))
        self._fitter = value
    fit = property(fget=lambda self: self._fitter, fset=_set_fitter)
    TRANSPORTS = 'amqp','mp','mpi'
    _transport = 'mp'
    def _set_transport(self, value):
        if value not in self.TRANSPORTS:
            raise ValueError("unknown transport %s; use %s"
                             %(value,"|".join(self.TRANSPORTS)))
        self._transport = value
    transport = property(fget=lambda self: self._transport, fset=_set_transport)
    meshsteps = 40

def getopts():
    opts = Refl1dOpts(sys.argv)
    opts.resynth = int(opts.resynth)
    opts.seed = int(opts.seed) if opts.seed != "" else None
    fitters.FIT_DEFAULT = opts.fit
    FIT_OPTIONS[opts.fit].set_from_cli(opts)
    return opts

# ==== Main ====

def initial_model(opts):
    if opts.seed is not None:
        numpy.random.seed(opts.seed)

    if opts.args:
        problem = load_problem(opts.args)
        if opts.pars is not None:
            recall_best(problem, opts.pars)
        if opts.random:
            problem.randomize()
        if opts.simulate:
            problem.simulate_data(noise=float(opts.noise))
            # If fitting, then generate a random starting point different
            # from the simulation
            if not (opts.check or opts.preview):
                problem.randomize()
    else:
        problem = None
    return problem

def resynth(problem, mapper, opts):
    make_store(problem,opts,exists_handler=store_overwrite_query)
    fid = open(problem.output_path+".rsy",'at')
    fitter.mapper = mapper.start_mapper(problem, opts.args)
    for i in range(opts.resynth):
        problem.resynth_data()
        best, fbest = fitter.fit()
        print "found %g"%fbest
        fid.write('%.15g '%fbest)
        fid.write(' '.join('%.15g'%v for v in best))
        fid.write('\n')
    problem.restore_data()
    fid.close()

def main():
    if len(sys.argv) == 1:
        sys.argv.append("-?")
        print "\nNo modelfile parameter was specified.\n"

    opts = getopts()

    # Set up the matplotlib backend to minimize the wx dependency.
    import matplotlib
    if opts.batch or opts.remote:
        matplotlib.use('Agg')
    else:
        matplotlib.use('WXAgg')
    matplotlib.interactive(False)

    problem = initial_model(opts)

    # TODO: AMQP mapper as implemented requires workers started up with
    # the particular problem; need to be able to transport the problem
    # to the worker instead.  Until that happens, the GUI shouldn't use
    # the AMQP mapper.
    if opts.parallel or opts.worker:
        if opts.transport == 'amqp':
            mapper = AMQPMapper
        elif opts.transport == 'mp':
            mapper = MPMapper
        elif opts.transport == 'mpi':
            raise NotImplementedError("mpi transport not implemented")
    else:
        mapper = SerialMapper

    fitopts = FIT_OPTIONS[opts.fit]
    fitter = FitDriver(fitopts.fitter, problem=problem, **fitopts.options)

    # Which format to view the plots

    Probe.view = opts.plot

    if opts.profile:
        run_profile(problem, steps=opts.steps)
    elif opts.worker:
        mapper.start_worker(problem)
    elif opts.check:
        if opts.cov: print problem.cov()
        print "chisq",problem()
    elif opts.preview:
        if opts.cov: print problem.cov()
        preview(problem)
    elif opts.resynth > 0:
        resynth(problem, mapper, opts)

    elif opts.remote:

        # Check that problem runs before submitting it remotely
        chisq = problem()
        print "initial chisq:", chisq
        job = start_remote_fit(problem, opts,
                               queue=opts.queue, notify=opts.notify)
        print "remote job:", job['id']

    else:
        make_store(problem,opts,exists_handler=store_overwrite_query)

        # Show command line arguments and initial model
        print "#"," ".join(sys.argv)
        problem.show()
        if opts.stepmon:
            fid = open(problem.output_path+'.log', 'w')
            fitter.monitors = [ConsoleMonitor(problem),
                               StepMonitor(problem,fid,fields=['step','value'])]

        fitter.mapper = mapper.start_mapper(problem, opts.args)
        best, fbest = fitter.fit()
        remember_best(fitter, problem, best)
        if opts.cov: print cov(problem)
        if not opts.batch:
            import pylab
            pylab.show()

# Allow  "$python -m refl1d.cli args" calling pattern
if __name__ == "__main__": main()
