import sys, os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '..'))

from trainerV2.Robust_PPO.PPO_continuous_main import PPO_GameAgent
# from scripts.continuous.test_moving import env_list
from scripts.data.test_stationary import env_list
from utils import tools


if __name__ == "__main__":
    tools.setup_seed(10)
    dirs = {}
    dirs['actor'] = 'cache/results/ppo_stationary_robust/model/'
    dirs['critic'] = 'cache/results/ppo_stationary_robust/model/'
    dirs['adv_net'] = 'cache/results/ppo_stationary_robust/model/'

    save_dir = 'cache/results/ppo_stationary_evaluation/robust_adv/'
    tools.mkdir(save_dir)
    args = tools.load_config("configs/config_ppo_default.yaml")
    args = tools.dict2class(args)
    PPO_agent = PPO_GameAgent(args=args, output_dir=save_dir)
    PPO_agent.robust_evaluation(env=env_list.environment_list[0], dirs=dirs, noise_type='adv')