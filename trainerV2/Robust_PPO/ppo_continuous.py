import torch
import torch.nn.functional as F
from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler
import torch.nn as nn
from torch.distributions import Beta, Normal
from utils import tools
import os
from trainerV2.Robust_PPO import adversarial


# Trick 8: orthogonal initialization
def orthogonal_init(layer, gain=1.0):
    nn.init.orthogonal_(layer.weight, gain=gain)
    nn.init.constant_(layer.bias, 0)


class Actor_Beta(nn.Module):
    def __init__(self, args, name='actor_beta', chkpt_dir='cache/model/ppo'):
        super(Actor_Beta, self).__init__()
        self.device = args.device
        self.fc1 = nn.Linear(args.state_dim, args.hidden_width)
        self.fc2 = nn.Linear(args.hidden_width, args.hidden_width)
        self.alpha_layer = nn.Linear(args.hidden_width, args.action_dim)
        self.beta_layer = nn.Linear(args.hidden_width, args.action_dim)
        self.activate_func = [nn.ReLU(), nn.Tanh()][args.use_tanh]  # Trick10: use tanh

        self.name = name
        self.checkpoint_file = os.path.join(chkpt_dir, name)
        self.num_checkpoints = 0
        self.to(self.device)

        if args.use_orthogonal_init:
            print("------use_orthogonal_init------")
            orthogonal_init(self.fc1)
            orthogonal_init(self.fc2)
            orthogonal_init(self.alpha_layer, gain=0.01)
            orthogonal_init(self.beta_layer, gain=0.01)

    def forward(self, s):
        s = torch.tensor(s).to(self.device)
        s = self.activate_func(self.fc1(s))
        s = self.activate_func(self.fc2(s))
        # alpha and beta need to be larger than 1,so we use 'softplus' as the activation function and then plus 1
        alpha = F.softplus(self.alpha_layer(s)) + 1.0
        beta = F.softplus(self.beta_layer(s)) + 1.0
        return alpha.cpu(), beta.cpu()

    def get_dist(self, s):
        alpha, beta = self.forward(s)
        dist = Beta(alpha, beta)
        return dist.cpu()

    def mean(self, s):
        alpha, beta = self.forward(s)
        mean = alpha / (alpha + beta)  # The mean of the beta distribution
        return mean.cpu()

    def save_checkpoint(self, mode = 'Default'):
        self.num_checkpoints += 1
        tools.save_network_params(mode=mode, checkpoint_file=self.checkpoint_file, 
                                    state_dict=self.state_dict())

    def load_checkpoint(self, mode = 'Default', chkpt_dir=None):
        if chkpt_dir != None:
            self.checkpoint_file = chkpt_dir + self.name
        state_dict = tools.load_network_params(mode=mode, checkpoint_file=self.checkpoint_file)
        self.load_state_dict(state_dict)

class Actor_Gaussian(nn.Module):
    def __init__(self, args, name='actor_gaussian', chkpt_dir='cache/model/ppo'):
        super(Actor_Gaussian, self).__init__()
        self.device = args.device
        self.max_action = args.max_action
        self.fc1 = nn.Linear(args.state_dim, args.hidden_width)
        self.fc2 = nn.Linear(args.hidden_width, args.hidden_width)
        self.mean_layer = nn.Linear(args.hidden_width, args.action_dim)
        self.log_std = nn.Parameter(torch.zeros(1, args.action_dim))  # We use 'nn.Parameter' to train log_std automatically
        self.activate_func = [nn.ReLU(), nn.Tanh()][args.use_tanh]  # Trick10: use tanh

        self.name = name
        self.checkpoint_file = os.path.join(chkpt_dir, name)
        self.num_checkpoints = 0
        self.to(self.device)

        if args.use_orthogonal_init:
            print("------use_orthogonal_init------")
            orthogonal_init(self.fc1)
            orthogonal_init(self.fc2)
            orthogonal_init(self.mean_layer, gain=0.01)

    def forward(self, s):
        s = torch.tensor(s).to(self.device)
        s = self.activate_func(self.fc1(s))
        s = self.activate_func(self.fc2(s))
        # mean = self.max_action * torch.tanh(self.mean_layer(s))  # [-1,1]->[-max_action,max_action]
        mean = 1/2 * (self.max_action * torch.tanh(self.mean_layer(s)) + self.max_action) # [-1,1]->[0,max_action]
        return mean.cpu()

    def get_dist(self, s):
        mean = self.forward(s)
        log_std = self.log_std.expand_as(mean).cpu()  # To make 'log_std' have the same dimension as 'mean'
        std = torch.exp(log_std)  # The reason we train the 'log_std' is to ensure std=exp(log_std)>0
        dist = Normal(mean, std)  # Get the Gaussian distribution
        return dist

    def get_dist_parameter(self, s):
        mean = self.forward(s)
        log_std = self.log_std.expand_as(mean).cpu()  # To make 'log_std' have the same dimension as 'mean'
        std = torch.exp(log_std)  # The reason we train the 'log_std' is to ensure std=exp(log_std)>0
        return mean, std

    def save_checkpoint(self, mode = 'Default'):
        self.num_checkpoints += 1
        tools.save_network_params(mode=mode, checkpoint_file=self.checkpoint_file, 
                                    state_dict=self.state_dict())

    def load_checkpoint(self, mode = 'Default', chkpt_dir=None):
        if chkpt_dir != None:
            self.checkpoint_file = chkpt_dir + self.name
        state_dict = tools.load_network_params(mode=mode, checkpoint_file=self.checkpoint_file)
        self.load_state_dict(state_dict)

class Critic(nn.Module):
    def __init__(self, args, name='critic', chkpt_dir='model/ppo'):
        super(Critic, self).__init__()
        self.device = args.device
        self.fc1 = nn.Linear(args.state_dim, args.hidden_width)
        self.fc2 = nn.Linear(args.hidden_width, args.hidden_width)
        self.fc3 = nn.Linear(args.hidden_width, 1)
        self.activate_func = [nn.ReLU(), nn.Tanh()][args.use_tanh]  # Trick10: use tanh

        self.checkpoint_file = os.path.join(chkpt_dir, name)
        self.num_checkpoints = 0
        self.to(self.device)

        self.name = name
        if args.use_orthogonal_init:
            print("------use_orthogonal_init------")
            orthogonal_init(self.fc1)
            orthogonal_init(self.fc2)
            orthogonal_init(self.fc3)

    def forward(self, s):
        s = torch.tensor(s).to(self.device)
        s = self.activate_func(self.fc1(s))
        s = self.activate_func(self.fc2(s))
        v_s = self.fc3(s)
        return v_s.cpu()

    def save_checkpoint(self, mode = 'Default'):
        self.num_checkpoints += 1
        tools.save_network_params(mode=mode, checkpoint_file=self.checkpoint_file, 
                                    state_dict=self.state_dict())

    def load_checkpoint(self, mode = 'Default', chkpt_dir=None):
        if chkpt_dir != None:
            self.checkpoint_file = chkpt_dir + self.name
        state_dict = tools.load_network_params(mode=mode, checkpoint_file=self.checkpoint_file)
        self.load_state_dict(state_dict)

class PPO_continuous():
    def __init__(self, args, chkpt_dir, train_adv=False, load_model=None):
        self.policy_dist = args.policy_dist
        self.max_action = args.max_action
        self.batch_size = args.batch_size
        self.mini_batch_size = args.mini_batch_size
        self.max_train_steps = args.max_train_steps
        self.lr_a = args.lr_a  # Learning rate of actor
        self.lr_c = args.lr_c  # Learning rate of critic
        self.gamma = args.gamma  # Discount factor
        self.lamda = args.lamda  # GAE parameter
        self.epsilon = args.epsilon  # PPO clip parameter
        self.K_epochs = args.K_epochs  # PPO parameter
        self.entropy_coef = args.entropy_coef  # Entropy coefficient
        self.set_adam_eps = args.set_adam_eps
        self.use_grad_clip = args.use_grad_clip
        self.use_lr_decay = args.use_lr_decay
        self.use_adv_norm = args.use_adv_norm
        self.adv_loss = 0

        self.train_adv = train_adv
        
        if self.policy_dist == "Beta":
            self.actor = Actor_Beta(args, chkpt_dir=chkpt_dir)
        else:
            self.actor = Actor_Gaussian(args, chkpt_dir=chkpt_dir)

        self.critic = Critic(args, chkpt_dir=chkpt_dir)
        self.adv_net = adversarial.Net(args, chkpt_dir=chkpt_dir)

        if load_model != None:
            self.load_models()
            
        if self.set_adam_eps:  # Trick 9: set Adam epsilon=1e-5
            self.optimizer_actor = torch.optim.Adam(self.actor.parameters(), lr=self.lr_a, eps=1e-5)
            self.optimizer_critic = torch.optim.Adam(self.critic.parameters(), lr=self.lr_c, eps=1e-5)
        else:
            self.optimizer_actor = torch.optim.Adam(self.actor.parameters(), lr=self.lr_a)
            self.optimizer_critic = torch.optim.Adam(self.critic.parameters(), lr=self.lr_c)

    def evaluate(self, s):  # When evaluating the policy, we only use the mean
        s = torch.unsqueeze(torch.tensor(s, dtype=torch.float), 0)
        if self.policy_dist == "Beta":
            a = self.actor.mean(s).detach().numpy().flatten()
        else:
            a = self.actor(s).detach().numpy().flatten()
        return a

    def choose_action(self, s):
        s = torch.unsqueeze(torch.tensor(s, dtype=torch.float), 0)
        if self.policy_dist == "Beta":
            with torch.no_grad():
                dist = self.actor.get_dist(s)
                a = dist.sample()  # Sample the action according to the probability distribution
                a_logprob = dist.log_prob(a)  # The log probability density of the action
        else:
            with torch.no_grad():
                dist = self.actor.get_dist(s)
                a = dist.sample()  # Sample the action according to the probability distribution
                # a = torch.clamp(a, -self.max_action, self.max_action)  # [-max,max]
                a = torch.clamp(a, 0, self.max_action) # [0,max]
                a_logprob = dist.log_prob(a)  # The log probability density of the action
        return a.numpy().flatten(), a_logprob.numpy().flatten()

    def guassian_kl(self, u1, sigma1, u2, sigma2):
        loss = torch.div(torch.square(u1 - u2) + torch.square(sigma1) - torch.square(sigma2), 2*torch.square(sigma2)) + torch.log(torch.div(sigma2,sigma1))
        return torch.mean(loss, dim=1).unsqueeze(dim=1)

    def guassian_jeffrey(self, parameters_1, parameters_2):
        [u1, sigma1] = parameters_1
        [u2, sigma2] = parameters_2
        return self.guassian_kl(u1, sigma1, u2, sigma2)/2 + self.guassian_kl(u2, sigma2, u1, sigma1)/2

    def update(self, replay_buffer, total_steps):
        s, a, a_logprob, r, s_, dw, done = replay_buffer.numpy_to_tensor()  # Get training data
        """
            Calculate the advantage using GAE
            'dw=True' means dead or win, there is no next state s'
            'done=True' represents the terminal of an episode(dead or win or reaching the max_episode_steps). When calculating the adv, if done=True, gae=0
        """
        adv = []
        gae = 0
        with torch.no_grad():  # adv and v_target have no gradient
            vs = self.critic(s)
            vs_ = self.critic(s_)
            deltas = r + self.gamma * (1.0 - dw) * vs_ - vs
            for delta, d in zip(reversed(deltas.flatten().numpy()), reversed(done.flatten().numpy())):
                gae = delta + self.gamma * self.lamda * gae * (1.0 - d)
                adv.insert(0, gae)
            adv = torch.tensor(adv, dtype=torch.float).view(-1, 1)
            v_target = adv + vs
            if self.use_adv_norm:  # Trick 1:advantage normalization
                adv = ((adv - adv.mean()) / (adv.std() + 1e-5))

        if self.train_adv:
            perturb = self.adv_net(s)
            perturb_state = s + perturb
            loss = - self.guassian_jeffrey(self.actor.get_dist_parameter(s), self.actor.get_dist_parameter(perturb_state))
            # loss = torch.tensor(loss, grad_fn=perturb_state.grad_fn)
            self.adv_net.optimizer.zero_grad()
            loss.mean().backward()
            self.adv_net.optimizer.step()
            perturb = self.adv_net(s)
            perturb_state = s + perturb
            self.adv_loss = loss.mean(dtype=torch.float32)
        
        # Optimize policy for K epochs:
        for _ in range(self.K_epochs):
            # Random sampling and no repetition. 'False' indicates that training will continue even if the number of samples in the last time is less than mini_batch_size
            for index in BatchSampler(SubsetRandomSampler(range(self.batch_size)), self.mini_batch_size, False):
                dist_now = self.actor.get_dist(s[index])
                dist_entropy = dist_now.entropy().sum(1, keepdim=True)  # shape(mini_batch_size X 1)
                a_logprob_now = dist_now.log_prob(a[index])
                # a/b=exp(log(a)-log(b))  In multi-dimensional continuous action space，we need to sum up the log_prob
                ratios = torch.exp(a_logprob_now.sum(1, keepdim=True) - a_logprob[index].sum(1, keepdim=True))  # shape(mini_batch_size X 1)

                surr1 = ratios * adv[index]  # Only calculate the gradient of 'a_logprob_now' in ratios
                surr2 = torch.clamp(ratios, 1 - self.epsilon, 1 + self.epsilon) * adv[index]
                actor_loss = -torch.min(surr1, surr2) - self.entropy_coef * dist_entropy # Trick 5: policy entropy

                if self.train_adv:
                    with torch.no_grad():
                        extra_loss = self.guassian_jeffrey(self.actor.get_dist_parameter(s[index]), self.actor.get_dist_parameter(perturb_state[index]))
                    actor_loss += extra_loss
                # Update actor
                self.optimizer_actor.zero_grad()
                actor_loss.mean().backward()
                if self.use_grad_clip:  # Trick 7: Gradient clip
                    torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 0.5)
                self.optimizer_actor.step()

                v_s = self.critic(s[index])
                critic_loss = F.mse_loss(v_target[index], v_s)
                # Update critic
                self.optimizer_critic.zero_grad()
                critic_loss.backward()
                if self.use_grad_clip:  # Trick 7: Gradient clip
                    torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 0.5)
                self.optimizer_critic.step()

            # self.actor.save_checkpoint(mode=self.env_type)
            # self.critic.save_checkpoint(mode=self.env_type)

        if self.use_lr_decay:  # Trick 6:learning rate Decay
            self.lr_decay(total_steps)

    def lr_decay(self, total_steps):
        lr_a_now = self.lr_a * (1 - total_steps / self.max_train_steps)
        lr_c_now = self.lr_c * (1 - total_steps / self.max_train_steps)
        for p in self.optimizer_actor.param_groups:
            p['lr'] = lr_a_now
        for p in self.optimizer_critic.param_groups:
            p['lr'] = lr_c_now
            
    def save_models(self, mode = 'Default'):
        self.actor.save_checkpoint(mode=mode)
        self.critic.save_checkpoint(mode=mode)
        if self.train_adv:
            self.adv_net.save_checkpoint(mode=mode)

    def load_models(self, mode = 'Default'):
        self.actor.load_checkpoint(mode=mode)
        self.critic.load_checkpoint(mode=mode)
        self.adv_net.load_checkpoint(mode=mode)