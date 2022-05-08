from trainer.dqn import DQN, MEMORY_CAPACITY
from environments.DQN_Environment import DQN_Environment

def init_env():
    board = [[0, 0, 0, 0, 0],
            [0, 3, 0, 0, 0],
            [0, 0, 0, 1, 0],
            [0, 0, 2, 0, 0],
            [0, 0, 0, 0, 0]]
    startAt = [0 ,0]
    arrivalAt = [4,4]
    env = DQN_Environment(board=board)
    data_volumn = [100, 100, 100]
    env.init(startAt=startAt, arrivalAt=arrivalAt, data_volume=data_volumn)
    return env

if __name__ == "__main__":                            
    env = init_env()
    dqn = DQN(5, 5, env.get_action_space().n(), env=env)

    for i in range(400):
        print('<<<<<<<<<Episode: %s' % i)
        s, current_position = env.reset()
        episode_reward_sum = 0

        while True:
            # env.render()
            a = dqn.choose_action(s, current_position)
            s_, r, done, current_position = env.step(a)

            '''
            # 修改奖励 (不修改也可以，修改奖励只是为了更快地得到训练好的摆杆)
            x, x_dot, theta, theta_dot = s_
            r1 = (env.x_threshold - abs(x)) / env.x_threshold - 0.8
            r2 = (env.theta_threshold_radians - abs(theta)) / env.theta_threshold_radians - 0.5
            new_r = r1 + r2
            '''

            dqn.store_transition(s, a, r, s_, done)
            episode_reward_sum += r

            s = s_

            if dqn.memory_counter > MEMORY_CAPACITY:
                dqn.learn()

            if done:
                print('episode%s---reward_sum: %s' % (i, round(episode_reward_sum, 2)))
                break