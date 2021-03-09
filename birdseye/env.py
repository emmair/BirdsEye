import numpy as np 
import random 
from pfilter import ParticleFilter, systematic_resample


# Some transform functions
# to be abstracted out later
def pol2cart(rho, phi):
    x = rho * np.cos(phi)
    y = rho * np.sin(phi)
    return(x, y)

class RFEnv(object): 

    def __init__(self, sensor): 
        
        self.sensor = sensor 
        # Action space and function to convert from action to index and vice versa
        self.action_space = ((-30,1), (-30, 2), (0, 1), (0, 2), (30, 1), (30, 2))


    def dynamics(self, particles, control=None, **kwargs):
        return np.array([list(self.f(p, control)) for p in particles])

    def reset(self): 

        self.iters = 0
        self.true_state = np.array([random.randint(25,100), random.randint(0,359), random.randint(0,11)*30, 1])

        num_particles=500
        self.pf = ParticleFilter(
                        prior_fn=lambda n: np.array([self.sensor.near_state(self.true_state) for i in range(n)]),
                        observe_fn=lambda states, **kwargs: np.array([np.array(self.sensor.observation(x)) for x in states]),
                        n_particles=num_particles,
                        #dynamics_fn=lambda particles, **kwargs: [f2(p, control) for p in particles],
                        dynamics_fn=self.dynamics,
                        noise_fn=lambda x, **kwargs: x,
                        #noise_fn=lambda x:
                        #            gaussian_noise(x, sigmas=[0.2, 0.2, 0.1, 0.05, 0.05]),
                        weight_fn=lambda hyp, o, xp=None,**kwargs: [self.sensor.weight(None, o, xp=x) for x in xp],
                        resample_fn=systematic_resample,
                        column_names = ['range', 'bearing', 'relative_course', 'own_speed'])
        
        #return self.sensor.observation(self.true_state)
        env_obs = self.env_observation()
        return env_obs

    #returns action given an index
    def action_to_index(self, a):
        return int(np.trunc(2*(a[0] / 30 + 1) + a[1]))-1

    #returns index of action given an action
    def index_to_action(self, a):
        a = a + 1
        if a % 2 == 0:
            return (int(np.trunc((((a - 2) / 2) - 1) * 30)), 2)
        else:
            return (int(np.trunc((((a - 1) / 2) - 1) * 30)), 1)


    # generate next course given current course
    def next_crs(self, crs, prob=0.9):
        if random.random() < prob:
            return crs
        crs = (crs + random.choice([-1,1])*30) % 360
        if crs < 0:
            crs += 360
        return crs


    # returns new state given last state and action (control)
    def f(self, state, control):
        TGT_SPD = 1
        r, theta, crs, spd = state
        spd = control[1]
        
        theta = theta % 360
        theta -= control[0]
        theta = theta % 360
        if theta < 0:
            theta += 360

        crs = crs % 360
        crs -= control[0]
        if crs < 0:
            crs += 360
        crs = crs % 360

        x, y = pol2cart(r, np.pi / 180 * theta)
        #x = r*np.cos(np.pi / 180 * theta)
        #y = r*np.sin(np.pi / 180 * theta)

        dx, dy = pol2cart(TGT_SPD, np.pi / 180 * crs)
        pos = [x + dx - spd, y + dy]

        #pos = [x + TGT_SPD * np.cos(np.pi / 180 * crs) - spd,
        #       y + TGT_SPD * np.sin(np.pi / 180 * crs)]
        crs = self.next_crs(crs)

        r = np.sqrt(pos[0]**2 + pos[1]**2)
        theta = np.arctan2(pos[1], pos[0]) * 180 / np.pi
        if theta < 0:
            theta += 360
        return (r, theta, crs, spd)


    # returns reward as a function of range, action, and action penalty or as a function of range only
    def reward_func(self, s, u=None, action_penalty=-.05):
        state_range = s[0]

        if u is not None: # returns reward as a function of range, action, and action penalty
            if (2 < u < 5):
                action_penalty = 0
            if state_range >= 150:
                return (-2 + action_penalty) # reward to not lose track of contact
            if state_range <= 10:
                return (-2 + action_penalty) # collision avoidance
            return (0.1 + action_penalty) # being in "sweet spot" maximizes reward
        else: # returns reward as a function of range only
            if state_range >= 150:
                return -2 # reward to not lose track of contact
            if state_range <= 10:
                return -200 # collision avoidance
            return 0.1 # being in "sweet spot" maximizes reward

    # returns observation, reward, done, info
    def step(self, action): 

        next_state = self.f(self.true_state, self.index_to_action(action))
        observation = self.sensor.observation(next_state)
        self.pf.update(np.array(observation), xp=self.pf.particles, control=self.index_to_action(action))
        
        reward = self.reward_func(next_state, action)
        self.true_state = next_state

        env_obs = self.env_observation()
        self.iters += 1 
        info = {'episode':{}}
        info['episode']['l'] = self.iters
        info['episode']['r'] = reward
        return (env_obs, reward, 0, info)

    def env_observation(self): 
        return np.expand_dims(self.particle_heatmap_obs(self.pf.particles), axis=0)
        
    def particle_heatmap_obs(self, belief):

        cart  = np.array(list(map(pol2cart, belief[:,0], belief[:,1]*np.pi/180)))
        x = cart[:,0]
        y = cart[:,1]
        heatmap, xedges, yedges = np.histogram2d(x, y, bins=100)

        return heatmap