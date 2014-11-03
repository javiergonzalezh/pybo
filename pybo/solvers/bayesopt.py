"""
Solver method for GP-based optimization which uses an inner-loop optimizer to
maximize some acquisition function, generally given as a simple function of the
posterior sufficient statistics.
"""

# future imports
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

# global imports
import numpy as np
import pygp

# exported symbols
__all__ = ['solve_bayesopt']


### HELPERS ###################################################################

def _make_dict(module, lstrip='', rstrip=''):
    """
    Given a module return a dictionary mapping the name of each of its exported
    functions to the function itself.
    """
    def generator():
        """Generate the (name, function) tuples."""
        for fname in module.__all__:
            f = getattr(module, fname)
            if fname.startswith(lstrip):
                fname = fname[len(lstrip):]
            if fname.endswith(rstrip):
                fname = fname[::-1][len(rstrip):][::-1]
            fname = fname.lower()
            yield fname, f
    return dict(generator())


### SOLVER COMPONENTS #########################################################

# each method/class defined exported by these modules will be exposed as a
# string to the solve_bayesopt method so that we can swap in/out different
# components for the "meta" solver.
from .. import globalopt as solvers
from . import init as initializers
from . import policies
from . import recommenders

POLICIES = _make_dict(policies)
INITIALIZERS = _make_dict(initializers, lstrip='init_')
SOLVERS = _make_dict(solvers, lstrip='solve_')
RECOMMENDERS = _make_dict(recommenders, lstrip='best_')


### THE BAYESOPT META SOLVER ##################################################

def solve_bayesopt(f,
                   bounds,
                   T=100,
                   policy='ei',
                   init='middle',
                   solver='lbfgs',
                   recommender='latent',
                   model=None,
                   callback=None):
    """
    Maximize the given function using Bayesian Optimization.
    """
    # make sure the bounds are a 2d-array.
    bounds = np.array(bounds, dtype=float, ndmin=2)

    # initialize all the solver components.
    policy = POLICIES[policy]
    init = INITIALIZERS[init]
    solver = SOLVERS[solver]
    recommender = RECOMMENDERS[recommender]

    # create a list of initial points to query.
    X = init(bounds)
    Y = [f(x) for x in X]

    if model is None:
        # initialize a bog-simple GP model.
        sn = 1e-3
        sf = np.std(Y) if (len(Y) > 1) else 10.
        mu = np.mean(Y)
        ell = bounds[:, 1] - bounds[:, 0]

        # specify a hyperprior for the GP.
        prior = {
            'sn': pygp.priors.Horseshoe(scale=0.1, min=1e-6),
            'sf': pygp.priors.LogNormal(mu=np.log(sf), sigma=1., min=1e-6),
            'ell': pygp.priors.Uniform(ell / 100, ell * 2),
            'mu': pygp.priors.Gaussian(mu, sf)}

        # create the GP model (with hyperprior).
        model = pygp.BasicGP(sn, sf, ell, mu, kernel='matern5')
        model = pygp.meta.MCMC(model, prior, n=10, burn=100)

    # add any initial data to our model.
    model.add_data(X, Y)

    # allocate a datastructure containing "convergence" info.
    info = np.zeros(T, [('x', np.float, (len(bounds),)),
                        ('y', np.float),
                        ('xbest', np.float, (len(bounds),)),
                        ('fbest', np.float)])

    # initialize the data.
    info[:] = np.nan
    info['x'][:len(X)] = X
    info['y'][:len(Y)] = Y

    for i in xrange(model.ndata, T):
        # get the next point to evaluate.
        index = policy(model)
        x, _ = solver(index, bounds, maximize=True)

        # deal with any visualization.
        if callback is not None:
            callback(info[:i], x, f, model, bounds, index)

        # make an observation and record it.
        y = f(x)
        model.add_data(x, y)

        # find our next recommendation and evaluate it if possible.
        xbest = recommender(model, bounds)
        fbest = f.get_f(xbest[None])[0] if hasattr(f, 'get_f') else np.nan

        # record everything.
        info[i] = (x, y, xbest, fbest)

    return info
