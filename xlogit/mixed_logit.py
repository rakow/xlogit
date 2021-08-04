"""Implements all the logic for mixed logit models."""

# pylint: disable=invalid-name
import scipy.stats
from scipy.optimize import minimize
from ._choice_model import ChoiceModel
from ._device import device as dev
import numpy as np

"""
Notations
---------
    N : Number of choice situations
    P : Number of observations per panel
    J : Number of alternatives
    K : Number of variables (Kf: fixed, Kr: random)
"""

MIN_COMP_ZERO = 1e-300
MAX_COMP_EXP = 700

class MixedLogit(ChoiceModel):
    """Class for estimation of Mixed Logit Models.

    Attributes
    ----------
        coeff_ : numpy array, shape (n_variables + n_randvars, )
            Estimated coefficients

        coeff_names : numpy array, shape (n_variables + n_randvars, )
            Names of the estimated coefficients

        stderr : numpy array, shape (n_variables + n_randvars, )
            Standard errors of the estimated coefficients

        zvalues : numpy array, shape (n_variables + n_randvars, )
            Z-values for t-distribution of the estimated coefficients

        pvalues : numpy array, shape (n_variables + n_randvars, )
            P-values of the estimated coefficients

        loglikelihood : float
            Log-likelihood at the end of the estimation

        convergence : bool
            Whether convergence was reached during estimation

        total_iter : int
            Total number of iterations executed during estimation

        estim_time_sec : float
            Estimation time in seconds

        sample_size : int
            Number of samples used for estimation

        aic : float
            Akaike information criteria of the estimated model

        bic : float
            Bayesian information criteria of the estimated model
    """

    def __init__(self):
        """Init Function."""
        super(MixedLogit, self).__init__()
        self._rvidx = None  # Index of random variables (True when random var)
        self._rvdist = None  # List of mixing distributions of rand vars

    def fit(self, X, y, varnames, alts, ids, randvars, isvars=None, 
            weights=None, avail=None,  panels=None,
            base_alt=None, fit_intercept=False, init_coeff=None, maxiter=2000,
            random_state=None, n_draws=500, halton=True, verbose=1):
        """Fit Mixed Logit models.

        Parameters
        ----------
        X : array-like, shape (n_samples*n_alts, n_variables)
            Input data for explanatory variables in long format

        y : array-like, shape (n_samples*n_alts,)
            Chosen alternatives or one-hot encoded representation
            of the choices

        varnames : list-like, shape (n_variables,)
            Names of explanatory variables that must match the number and
            order of columns in ``X``

        alts : array-like, shape (n_samples*n_alts,)
            Alternative values in long format

        ids : array-like, shape (n_samples*n_alts,)
            Identifiers for the samples in long format.

        randvars : dict
            Names (keys) and mixing distributions (values) of variables that
            have random parameters as coefficients. Possible mixing
            distributions are: ``'n'``: normal, ``'ln'``: lognormal,
            ``'u'``: uniform, ``'t'``: triangular, ``'tn'``: truncated normal

        isvars : list-like
            Names of individual-specific variables in ``varnames``

        weights : array-like, shape (n_samples,), default=None
            Sample weights in long format.

        avail: array-like, shape (n_samples*n_alts,), default=None
            Availability of alternatives for the choice situations. One when
            available or zero otherwise.

        panels : array-like, shape (n_samples*n_alts,), default=None
            Identifiers in long format to create panels in combination with
            ``ids``

        base_alt : int, float or str, default=None
            Base alternative

        fit_intercept : bool, default=False
            Whether to include an intercept in the model.

        init_coeff : numpy array, shape (n_variables,), default=None
            Initial coefficients for estimation.

        maxiter : int, default=200
            Maximum number of iterations

        random_state : int, default=None
            Random seed for numpy random generator

        n_draws : int, default=500
            Number of random draws to approximate the mixing distributions of
            the random coefficients

        halton : bool, default=True
            Whether the estimation uses halton draws.

        verbose : int, default=1
            Verbosity of messages to show during estimation. 0: No messages,
            1: Some messages, 2: All messages


        Returns
        -------
        None.
        """
        # Handle array-like inputs by converting everything to numpy arrays
        X, y, varnames, alts, isvars, ids, weights, panels, avail\
            = self._as_array(X, y, varnames, alts, isvars, ids, weights,
                             panels, avail)

        self._validate_inputs(X, y, alts, varnames, isvars, ids, weights)
        
        self._pre_fit(alts, varnames, isvars, base_alt,
                      fit_intercept, maxiter)

        betas, X, y, panel_info, draws, weights, avail, Xnames = \
            self._setup_input_data(X, y, varnames, alts, ids, randvars, 
                                   isvars=isvars, weights=weights, avail=avail,
                                   panels=panels, init_coeff=init_coeff,
                                   random_state=random_state, n_draws=n_draws,
                                   halton=halton, verbose=verbose,
                                   predict_mode=False)

        optimizat_res = \
            minimize(self._loglik_gradient, betas, jac=True, method='BFGS',
                     args=(X, y, panel_info, draws, weights, avail), tol=1e-5,
                     options={'gtol': 1e-4, 'maxiter': maxiter,
                              'disp': verbose > 0})

        coef_names = np.append(Xnames, np.char.add("sd.", Xnames[self._rvidx]))

        self._post_fit(optimizat_res, coef_names, X.shape[0], verbose)


    def predict(self, X, varnames, alts, ids, isvars=None, weights=None,
                avail=None,  panels=None, random_state=None, n_draws=200,
                halton=True, verbose=1, return_proba=False,
                return_freq=False):
        """Predict chosen alternatives.

        Parameters
        ----------
        X : array-like, shape (n_samples*n_alts, n_variables)
            Input data for explanatory variables in long format

        varnames : list, shape (n_variables,)
            Names of explanatory variables that must match the number and
            order of columns in ``X``

        alts : array-like, shape (n_samples*n_alts,)
            Alternative values in long format

        ids : array-like, shape (n_samples*n_alts,)
            Identifiers for the samples in long format.

        isvars : list
            Names of individual-specific variables in ``varnames``

        weights : array-like, shape (n_variables,), default=None
            Sample weights in long format.

        avail: array-like, shape (n_samples*n_alts,), default=None
            Availability of alternatives for the samples. One when
            available or zero otherwise.

        panels : array-like, shape (n_samples*n_alts,), default=None
            Identifiers in long format to create panels in combination with
            ``ids``

        random_state : int, default=None
            Random seed for numpy random generator

        n_draws : int, default=200
            Number of random draws to approximate the mixing distributions of
            the random coefficients

        halton : bool, default=True
            Whether the estimation uses halton draws.

        verbose : int, default=1
            Verbosity of messages to show during estimation. 0: No messages,
            1: Some messages, 2: All messages
        
        return_proba : bool, default=False
            If True, also return the choice probabilities

        return_freq : bool, default=False
            If True, also return the frequency of the chosen the alternatives


        Returns
        -------
        choices : array-like, shape (n_samples, )
            Chosen alternative for every sample in the dataset.

        proba : array-like, shape (n_samples, n_alts), optional
            Choice probabilities for each sample in the dataset. The 
            alternatives are ordered (in the columns) as they appear
            in ``self.alternatives``. Only provided if
            `return_proba` is True.

        freq : dict, optional
            Choice frequency for each alternative. Only provided
            if `return_freq` is True.
        """
        # Handle array-like inputs by converting everything to numpy arrays
        #=== 1. Preprocess inputs
        X, _, varnames, alts, isvars, ids, weights, panels, avail\
            = self._as_array(X, None, varnames, alts, isvars, ids, weights,
                             panels, avail)
        
        self._validate_inputs(X, None, alts, varnames, isvars, ids, weights)
        
        betas, X, _, panel_info, draws, weights, avail, Xnames = \
            self._setup_input_data(X, None, varnames, alts, ids, self.randvars, 
                                   isvars=isvars, weights=weights, avail=avail,
                                   panels=panels, init_coeff=self.coeff_,
                                   random_state=random_state, n_draws=n_draws,
                                   halton=halton, verbose=verbose,
                                   predict_mode=True)
            
        coef_names = np.append(Xnames, np.char.add("sd.", Xnames[self._rvidx]))
        if not np.array_equal(coef_names, self.coeff_names):
            raise ValueError("The provided 'varnames' yield coefficient names "
                             "that are inconsistent with the stored "
                             "'self.coeff_names'")
        
        betas = dev.to_gpu(betas) if dev.using_gpu else betas
        
        #=== 2. Compute choice probabilities
        p = self._compute_probabilities(betas, X,
                                        panel_info, draws, avail)  # (N,P,J,R)
        
        p = self._prob_product_across_panels(p, panel_info)  # (N,J,R)
        proba = p.mean(axis=-1)   # (N,J)
        if dev.using_gpu:
            proba = dev.to_cpu(proba)
        
        #=== 3. Compute choices
        idx_max_proba = np.argmax(proba, axis=1)
        choices = self.alternatives[idx_max_proba]
        
        #=== 4. Arrange output depending on requested information
        output = (choices, )
        if return_proba:
            output += (proba, )
        
        if return_freq:
            alt_list, counts = np.unique(choices, return_counts=True)
            freq = dict(zip(list(alt_list),
                            list(np.round(counts/np.sum(counts), 3))))
            output += (freq, )
        
        _unpack_tuple = lambda x : x if len(x) > 1 else x[0]
        
        return _unpack_tuple(output) # Unpack before returning
 
    
    def _setup_input_data(self, X, y, varnames, alts, ids, randvars,
                          isvars=None, weights=None, avail=None, panels=None,
                          init_coeff=None, random_state=None, n_draws=200,
                          halton=True, verbose=1, predict_mode=False):
        if random_state is not None:
            np.random.seed(random_state)

        X, y, panels = self._arrange_long_format(X, y, ids, alts, panels)
        y = self._format_choice_var(y, alts) if not predict_mode else None
        X, Xnames = self._setup_design_matrix(X)
        self._model_specific_validations(randvars, Xnames)

        J, K, R = X.shape[1], X.shape[2], n_draws
        Kr = len(randvars)

        if panels is not None:  # If panel
            X, y, panel_info = self._balance_panels(X, y, panels)
            N, P = panel_info.shape
        else:
            N, P = X.shape[0], 1
            panel_info = np.ones((N, 1))

        # Reshape arrays in the format required for the rest of the estimation
        X = X.reshape(N, P, J, K)
        y = y.reshape(N, P, J, 1) if not predict_mode else None

        if not predict_mode:
            self._setup_randvars_info(randvars, Xnames)
        self.n_draws = n_draws
        self.verbose = verbose

        if weights is not None:
            weights = weights*(N/np.sum(weights))  # Normalize weights

        if avail is not None:
            avail = avail.reshape(N, P, J)

        # Generate draws
        draws = self._generate_draws(N, R, halton)  # (N,Kr,R)
        if init_coeff is None:
            betas = np.repeat(.1, K + Kr)
        else:
            betas = init_coeff
            if len(init_coeff) != K + Kr:
                raise ValueError("The size of init_coeff must be: " + K + Kr)

        # Move data to GPU if GPU is being used
        if dev.using_gpu:
            X = dev.to_gpu(X)
            y = dev.to_gpu(y) if not predict_mode else None
            panel_info = dev.to_gpu(panel_info)
            draws = dev.to_gpu(draws)
            if weights is not None:
                weights = dev.to_gpu(weights)
            if avail is not None:
                avail = dev.to_gpu(avail)
            if verbose > 0:
                print("GPU processing enabled.")
        return betas, X, y, panel_info, draws, weights, avail, Xnames


    def _setup_randvars_info(self, randvars, Xnames):
        self.randvars = randvars
        self._rvidx, self._rvdist = [], []
        for var in Xnames:
            if var in self.randvars.keys():
                self._rvidx.append(True)
                self._rvdist.append(self.randvars[var])
            else:
                self._rvidx.append(False)
        self._rvidx = np.array(self._rvidx)


    def _compute_probabilities(self, betas, X, panel_info, draws, avail):
        """Compute the standard logit-based probabilities.

        Random and fixed coefficients are handled separately.
        """
        Bf, Br = self._transform_betas(betas, draws)  # Get fixed and rand coef
        Xf = X[:, :, :, ~self._rvidx]  # Data for fixed coefficients
        Xr = X[:, :, :, self._rvidx]   # Data for random coefficients

        XBf = dev.np.einsum('npjk,k -> npj', Xf, Bf)  # (N,P,J)
        XBr = dev.np.einsum('npjk,nkr -> npjr', Xr, Br)  # (N,P,J,R)
        V = XBf[:, :, :, None] + XBr  # (N,P,J,R)
        
        #MAX_COMP_EXP = np.log(np.finfo(X.dtype).max)*.9  # ~700 for f64
        V[V > MAX_COMP_EXP] = MAX_COMP_EXP
        eV = dev.np.exp(V)

        if avail is not None:
            eV = eV*avail[:, :, :, None]  # Acommodate availablity of alts.

        sumeV = dev.np.sum(eV, axis=2, keepdims=True)
        #MIN_COMP_ZERO = np.finfo(X.dtype).max*.9  # ~1e-300 for float64
        sumeV[sumeV == 0] = MIN_COMP_ZERO # 
        p = eV/sumeV  # (N,P,J,R)
        p = p*panel_info[:, :, None, None]  # Zero for unbalanced panels
        return p  # (N,P,J,R)

    def _loglik_gradient(self, betas, X, y, panel_info, draws, weights, avail):
        """Compute the log-likelihood and gradient.

        Fixed and random parameters are handled separately to
        speed up the estimation and the results are concatenated.
        """
        betas = betas.astype(X.dtype)
        if dev.using_gpu:
            betas = dev.to_gpu(betas)
        p = self._compute_probabilities(betas, X, panel_info, draws, avail)
        # Probability of chosen alt
        pch = (y*p).sum(axis=2)  # (N,P,R)
        pch = self._prob_product_across_panels(pch, panel_info)  # (N,R)

        # Log-likelihood
        lik = pch.mean(axis=1)  # (N,)
        loglik = dev.np.log(lik)
        if weights is not None:
            loglik = loglik*weights
        loglik = loglik.sum()

        # Gradient
        Xf = X[:, :, :, ~self._rvidx]
        Xr = X[:, :, :, self._rvidx]

        ymp = y - p  # (N,P,J,R)
        # Gradient for fixed and random params
        gr_f = dev.np.einsum('npjr,npjk -> nkr', ymp, Xf)
        der = self._compute_derivatives(betas, draws)
        gr_b = dev.np.einsum('npjr,npjk -> nkr', ymp, Xr)*der
        gr_w = dev.np.einsum('npjr,npjk -> nkr', ymp, Xr)*der*draws
        # Multiply gradient by the chose prob. and dived by mean chose prob.
        gr_f = (gr_f*pch[:, None, :]).mean(axis=2)/lik[:, None]  # (N,Kf)
        gr_b = (gr_b*pch[:, None, :]).mean(axis=2)/lik[:, None]  # (N,Kr)
        gr_w = (gr_w*pch[:, None, :]).mean(axis=2)/lik[:, None]  # (N,Kr)
        # Put all gradients in a single array and aggregate them
        grad = self._concat_gradients(gr_f, gr_b, gr_w)  # (N,K)
        if weights is not None:
            grad = grad*weights[:, None]
        grad = grad.sum(axis=0)  # (K,)

        if dev.using_gpu:
            grad, loglik = dev.to_cpu(grad), dev.to_cpu(loglik)
        self.total_fun_eval += 1
        if self.verbose > 1:
            print("Evaluation {}  Log-Lik.={:.2f}".format(self.total_fun_eval,
                                                          -loglik))
        return -loglik, -grad

    def _concat_gradients(self, gr_f, gr_b, gr_w):
        idx = np.append(np.where(~self._rvidx)[0], np.where(self._rvidx)[0])
        gr_fb = np.concatenate((gr_f, gr_b), axis=1)[:, idx]
        return np.concatenate((gr_fb, gr_w), axis=1)

    def _prob_product_across_panels(self, prob, panel_info):
        if not np.all(panel_info):  # If panel unbalanced. Not all ones
            prob[panel_info==0, :] = 1  # Multiply by one when unbalanced
        prob = prob.prod(axis=1)  # (N,R)
        #MIN_COMP_ZERO = np.finfo(prob.dtype).max*.9  # ~1e-300 for float64
        prob[prob == 0] = MIN_COMP_ZERO
        return prob  # (N,R)

    def _apply_distribution(self, betas_random):
        """Apply the mixing distribution to the random betas."""
        for k, dist in enumerate(self._rvdist):
            if dist == 'ln':
                betas_random[:, k, :] = dev.np.exp(betas_random[:, k, :])
            elif dist == 'tn':
                betas_random[:, k, :] = betas_random[:, k, :] *\
                    (betas_random[:, k, :] > 0)
        return betas_random

    def _balance_panels(self, X, y, panels):
        """Balance panels if necessary and produce a new version of X and y.

        If panels are already balanced, the same X and y are returned. This
        also returns panel_info, which keeps track of the panels that needed
        balancing.
        """
        _, J, K = X.shape
        _, p_obs = np.unique(panels, return_counts=True)
        p_obs = (p_obs/J).astype(int)
        N = len(p_obs)  # This is the new N after accounting for panels
        P = np.max(p_obs)  # Panel length for all records

        if not np.all(p_obs[0] == p_obs):  # Balancing needed
            y = y.reshape(X.shape[0], J, 1) if y is not None else None
            Xbal, ybal = np.zeros((N*P, J, K)), np.zeros((N*P, J, 1))
            panel_info = np.zeros((N, P))
            cum_p = 0  # Cumulative sum of n_obs at every iteration
            for n, p in enumerate(p_obs):
                # Copy data from original to balanced version
                Xbal[n*P:n*P + p, :, :] = X[cum_p:cum_p + p, :, :]
                ybal[n*P:n*P + p, :, :] = y[cum_p:cum_p + p, :, :] \
                    if y is not None else None  # in predict mode
                panel_info[n, :p] = np.ones(p)
                cum_p += p

        else:  # No balancing needed
            Xbal, ybal = X, y
            panel_info = np.ones((N, P))
        ybal = ybal if y is not None else None  # in predict mode
        return Xbal, ybal, panel_info

    def _compute_derivatives(self, betas, draws):
        """Compute the derivatives based on the mixing distributions."""
        N, R, Kr = draws.shape[0], draws.shape[2], self._rvidx.sum()
        der = dev.np.ones((N, Kr, R), dtype=draws.dtype)
        if any(set(self._rvdist).intersection(['ln', 'tn'])):
            _, betas_random = self._transform_betas(betas, draws)
            for k, dist in enumerate(self._rvdist):
                if dist == 'ln':
                    der[:, k, :] = betas_random[:, k, :]
                elif dist == 'tn':
                    der[:, k, :] = 1*(betas_random[:, k, :] > 0)
        return der

    def _transform_betas(self, betas, draws):
        """Compute the products between the betas and the random coefficients.

        This method also applies the associated mixing distributions
        """
        # Extract coeffiecients from betas array
        betas_fixed = betas[np.where(~self._rvidx)[0]]
        br_mean = betas[np.where(self._rvidx)[0]]
        br_sd = betas[len(self._rvidx):]  # Last Kr positions
        # Compute: betas = mean + sd*draws
        betas_random = br_mean[None, :, None] + draws*br_sd[None, :, None]
        betas_random = self._apply_distribution(betas_random)
        return betas_fixed, betas_random

    def _generate_draws(self, sample_size, n_draws, halton=True):
        """Generate draws based on the given mixing distributions."""
        if halton:
            draws = self._get_halton_draws(sample_size, n_draws,
                                           len(self._rvdist))
        else:
            draws = self._get_random_draws(sample_size, n_draws,
                                           len(self._rvdist))

        for k, dist in enumerate(self._rvdist):
            if dist in ['n', 'ln', 'tn']:  # Normal based
                draws[:, k, :] = scipy.stats.norm.ppf(draws[:, k, :])
            elif dist == 't':  # Triangular
                draws_k = draws[:, k, :]
                draws[:, k, :] = (np.sqrt(2*draws_k) - 1)*(draws_k <= .5) +\
                    (1 - np.sqrt(2*(1 - draws_k)))*(draws_k > .5)
            elif dist == 'u':  # Uniform
                draws[:, k, :] = 2*draws[:, k, :] - 1

        return draws  # (N,Kr,R)

    def _get_random_draws(self, sample_size, n_draws, n_vars):
        """Generate random uniform draws between 0 and 1."""
        return np.random.uniform(size=(sample_size, n_vars, n_draws))

    def _get_halton_draws(self, sample_size, n_draws, n_vars, shuffled=False):
        """Generate halton draws between 0 and 1."""
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
                  53, 59, 61, 71, 73, 79, 83, 89, 97, 101, 103, 107,
                  109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167,
                  173, 179, 181, 191, 193, 197, 199]

        def halton_seq(length, prime=3, shuffled=False, drop=100):
            h = np.array([.0])
            t = 0
            while len(h) < length + drop:
                t += 1
                h = np.append(h, np.tile(h, prime-1) +
                              np.repeat(np.arange(1, prime)/prime**t, len(h)))
            seq = h[drop:length+drop]
            if shuffled:
                np.random.shuffle(seq)
            return seq

        draws = [halton_seq(sample_size*n_draws, prime=primes[i % len(primes)],
                            shuffled=shuffled).reshape(sample_size, n_draws)
                 for i in range(n_vars)]
        draws = np.stack(draws, axis=1)
        return draws  # (N,Kr,R)

    def _model_specific_validations(self, randvars, Xnames):
        """Conduct validations specific for mixed logit models."""
        if randvars is None:
            raise ValueError("The 'randvars' parameter is required for Mixed "
                             "Logit estimation")
        if not set(randvars.keys()).issubset(Xnames):
            raise ValueError("Some variable names in 'randvars' were not "
                             "found in the list of variable names")
        if not set(randvars.values()).issubset(["n", "ln", "t", "tn", "u"]):
            raise ValueError("Wrong mixing distribution found in 'randvars'. "
                             "Accepted distrubtions are n, ln, t, u, tn")

    def summary(self):
        """Show estimation results in console."""
        super(MixedLogit, self).summary()

    @staticmethod
    def check_if_gpu_available():
        """Check if GPU processing is available by running a quick estimation.

        Returns
        -------
        bool
            True if GPU processing is available, False otherwise.

        """
        n_gpus = dev.get_device_count()
        if n_gpus > 0:
            # Test a very simple example to see if CuPy is working
            X = np.array([[2, 1], [1, 3], [3, 1], [2, 4]])
            y = np.array([0, 1, 0, 1])
            alts = np.array([1, 2, 1, 2])
            ids = np.array([1, 2, 3, 4])
            model = MixedLogit()
            model.fit(X, y, varnames=["a", "b"], ids=ids, alts=alts,
                      randvars={'a': 'n', 'b': 'n'}, maxiter=0, n_draws=500,
                      verbose=0)
            print("{} GPU device(s) available. xlogit will use "
                  "GPU processing".format(n_gpus))
            return True
        else:
            print("*** No GPU device found. Verify CuPy is properly installed")
            return False
