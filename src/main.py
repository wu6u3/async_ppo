import gym
import numpy as np
import tensorflow as tf


class Policy(object):
    def __init__(self, obs_dim, act_dim, hid_units=30):

        self._build_graph(obs_dim, act_dim, hid_units)
        self._init_session()

    def _build_graph(self, obs_dim, act_dim, hid_units):
        self.g = tf.Graph()
        with self.g.as_default():
            self._placeholders(obs_dim, act_dim)
            self._policy_nn(hid_units, obs_dim, act_dim)
            self._logprob(act_dim)
            self._kl_entropy(act_dim)
            self._sample()
            self._loss_train_op()
            self.init = tf.global_variables_initializer()

    def _placeholders(self, obs_dim, act_dim):
        self.obs_ph = tf.placeholder(tf.float32, (None, obs_dim), 'obs')
        self.act_ph = tf.placeholder(tf.float32, (None, act_dim), 'act')
        self.advantages_ph = tf.placeholder(tf.float32, (None,), 'advantages')
        self.training_ph = tf.placeholder(tf.bool, (1,), 'training')
        self.beta_ph = tf.placeholder(tf.float32, (1,), 'beta')
        self.old_log_vars_ph = tf.placeholder(tf.float32, (act_dim,))
        self.old_means_ph = tf.placeholder(tf.float32, (None, act_dim))

    def _policy_nn(self, hid_units, obs_dim, act_dim):
        normed = tf.layers.batch_normalization(self.obs_ph, training=self.training_ph)
        hid1 = tf.layers.dense(normed, hid_units, tf.tanh,
                               kernel_initializer=tf.random_normal_initializer(
                                   stddev=(np.sqrt(2/obs_dim))),
                               name='hid1')
        self.means = tf.layers.dense(hid1, act_dim,
                                     kernel_initializer=tf.random_normal_initializer(
                                         stddev=(np.sqrt(2/obs_dim))),
                                     name='means')
        self.log_vars = tf.get_variable("log_vars", act_dim,
                                        initializer=tf.constant_initializer(0.0))

    def _logprob(self, act_dim):
        logp_act = -0.5 * (np.log(np.sqrt(2.0 * np.pi)) * act_dim)
        logp_act += -0.5 * tf.reduce_sum(self.log_vars)
        logp_act += -0.5 * tf.reduce_sum(tf.square(self.act_ph - self.means) /
                                         tf.exp(self.log_vars),
                                         axis=1, keep_dims=True)
        self.logp_act = logp_act

    def _kl_entropy(self, act_dim):
        det_cov_old = tf.exp(tf.reduce_sum(self.old_log_vars_ph))
        det_cov_new = tf.exp(tf.reduce_sum(self.log_vars))
        tr_old_new = tf.reduce_sum(tf.exp(self.old_log_vars_ph - self.log_vars))

        self.kl = 0.5 * (tf.log(det_cov_new) - tf.log(det_cov_old) + tr_old_new +
                         tf.reduce_mean(tf.square(self.means - self.old_means_ph) /
                                        tf.exp(self.log_vars)) - act_dim)
        self.entropy = 0.5 * (act_dim * (np.log(2 * np.pi) + 1) +
                              tf.reduce_mean(self.log_vars))

    def _sample(self):
        self.sampled_act = (self.means +
                            tf.exp(self.log_vars / 2.0) * tf.random_normal(shape=(act_dim,)))

    def _loss_train_op(self, lr=0.01, mom=0.9):
        self.loss = tf.reduce_mean(self.advantages_ph * self.logp_act)
        # beta_ph: hyper-parameter to control weight of kl-divergence loss
        self.loss += -tf.reduce_mean(self.beta_ph * self.kl)
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        optimizer = tf.train.MomentumOptimizer(lr, mom)
        with tf.control_dependencies(update_ops):
            self.train_op = optimizer.minimize(-self.loss)

    def _init_session(self):
        """ Launch TensorFlow session and initialize variables"""
        self.sess = tf.Session(graph=self.g)
        self.sess.run(self.init)

    def sample(self, obs):
        """ Draw sample from policy distribution"""
        feed_dict = {self.obs_ph: obs,
                     self.training_ph: False}

        return self.sess.run(self.sampled_act, feed_dict=feed_dict)

    def update(self, observes, actions, advantages, epochs=10):
        """ Perform policy update based on batch (size = N) of samples

        :param observes: NumPy shape = (N, obs_dim)
        :param actions: NumPy shape = (N, act_dim)
        :param advantages: NumPy shape = (N,)
        :return: dictionary of metrics
            'KLOldNew'
            'Entropy'
            'AvgLoss'
        """
        feed_dict = {self.obs_ph: observes,
                     self.act_ph: actions,
                     self.advantages_ph: advantages,
                     self.training_ph: False}
        old_means_np, old_log_vars_np = self.sess.run([self.means, self.log_vars],
                                                      feed_dict)
        for e in range(epochs):
            feed_dict[self.training_ph] = True
            feed_dict[self.old_log_vars_ph] = old_log_vars_np
            feed_dict[self.old_means_ph] = old_means_np
            _, loss = self.sess.run([self.train_op, self.loss], feed_dict)

        loss, entropy, kl = self.sess.run([self.loss, self.entropy, self.kl])

        return loss, entropy, kl

    def close_sess(self):
        self.sess.close()


class ValueFunction(object):

    def __init__(self, obs_dim, epochs=5, reg=1e-2, lr=1e-2):
        self._build_graph()
        self._init_sess()

    def fit(self, observes, disc_sum_rew):
        pass

    def predict(self, observes):
        pass

    def close_sess(self):
        pass


def init_gym(env_name='Pendulum-v0'):
    """

    :param env_name: str, OpenAI Gym environment name
    :return: 3-tuple
        env: ai gym environment
        obs_dim: observation dimensions
        act_dim: action dimensions
    """
    env = gym.make(env_name)
    obs_dim = env.observation_space.shape[0]
    act_dim = env.action_space.shape[0]

    return env, obs_dim, act_dim


def run_episode(env, policy, animate=False):
    """ Run single episode with option to animate

    :param env: ai gym environment
    :param policy: policy with "sample" method
    :param animate: boolean, True uses env.render() method to animate episode
    :return: 3-tuple of NumPy arrays
        observes: shape = (episode len, obs_dim)
        actions: shape = (episode len, act_dim)
        rewards: shape = (episode len,)
    """
    return None, None, None


def run_policy(env, policy, min_steps):
    """ Run policy and collect data for a minimum of min_steps

    :param env: ai gym environment
    :param policy: policy with "sample" method
    :param min_steps: minimum number of samples to collect, completes current
    episode after min_steps reached
    :return: list dictionaries, 1 dictionary per episode. Dict key/values:
        'observes' : NumPy array of states from episode
        'actions' : NumPy array of actions from episode
        'rewards' : NumPy array of (undiscounted) rewards from episode
    """
    # use run_episode
    return [None, None, None]


def view_policy(env, policy):
    """ Run policy and view using env.render() method

    :param env: ai gym environment
    :param policy: policy with "sample" method
    :return: None
    """
    # use run_episode


def add_disc_sum_rew(trajectories, gamma=1.0):
    """ Adds discounted sum of rewards to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'disc_sum_rew' key)
    """


def add_value(trajectories, val_func):
    """ Adds estimated value to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'value' key)
    """

def add_advantage(trajectories, val_func):
    """ Adds estimated advantage to all timesteps of all trajectories

    :param trajectories: as returned by run_policy()
    :return: None (mutates trajectories to add 'advantage' key)
    """

def build_train_set(trajectories):
    """ Concatenates all trajectories into single NumPy array with first
     dimension = N = total time steps across all trajectories

    :param trajectories: trajectories after processing by add_disc_sum_rew(),
     add_value(), add_advantage()
    :return: 4-tuple of NumPy arrays
    obs: shape = (N, obs_dim)
    actions: shape = (N, act_dim)
    advantages: shape = (N,)
    disc_sum_rew: shape = (N,)
    """
    return None, None, None, None

def disp_metrics(metrics):
    """Print metrics to stdout"""
    for key in metrics:
        print(key, ' ', metrics[key])

def main(num_iter=100,
         gamma=1.0):

    # launch ai gym env
    env, obs_dim, act_dim = init_gym()

    # init value function and policy
    val_func = ValueFunction(obs_dim)
    policy = Policy(obs_dim, act_dim)
    # main loop:
    for i in range(num_iter):
        # collect data batch using policy
        trajectories = run_policy(env, policy)
        # calculate cum_sum_rew: all time steps
        add_disc_sum_rew(trajectories, gamma)
        # value prediction: all time steps
        add_value(trajectories, val_func)
        # calculate advantages: cum_sum_rew - v(s_t)
        add_advantage(trajectories)
        # policy update
        observes, actions, advantages, disc_sum_rew = build_train_set(trajectories)
        metrics = policy.update(observes, actions, advantages)
        # fit value function
        metrics.update(val_func.fit(observes, disc_sum_rew))
        disp_metrics(metrics)
        # view policy
        view_policy(env, policy)

