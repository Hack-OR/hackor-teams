#!/usr/bin/env python3

import random
import copy
import math


SPECIALITIES = [ 'software', 'ui/ux', 'backend' ]
TEAM_SIZE = 2

repr_team = lambda team: (sorted([x['username'] for x in team]))

user_requests = [
    {
        'username': 'aaron',
        'specialities': [ 'software' ],
        'team_requests': [ 'vivian', 'joy', 'zander' ],
        'noob': False
    },
    {
        'username': 'joy',
        'specialities': [ 'ui/ux', 'software' ],
        'team_requests': [ 'aaron', 'vivian', 'derek' ],
        'noob': False
    },
    {
        'username': 'derek',
        'specialities': [ 'backend' ],
        'team_requests': [ 'joy', 'zander' ],
        'noob': False
    },
    {
        'username': 'vivian',
        'specialities': [],
        'team_requests': [ 'dan', 'aaron' ],
        'noob': False
    },
    {
        'username': 'zander',
        'specialities': [ 'ui/ux', 'backend' ],
        'team_requests': [ 'derek', 'bob', 'joy' ],
        'noob': True
    },

    {
        'username': 'bob',
        'specialities': [],
        'team_requests': [ 'aaron' ],
        'noob': True
    },
    {
        'username': 'dan',
        'specialities': [],
        'team_requests': [ 'zander', 'derek' ],
        'noob': True
    },
    {
        'username': 'kevin',
        'specialities': [ 'ui/ux' ],
        'team_requests': [],
        'noob': True
    }
]


def score_team(team: list) -> float:
    #assert len(team) == TEAM_SIZE
    team_size = len(team) # sometimes we just can't get the ideal number of people on a team

    # for keeping track of specialities counts and noobs later
    specialities = dict(zip(SPECIALITIES, [0]*len(SPECIALITIES)))
    noobs = list()

    # find speciality balances
    specialities_weight = 1
    for user in team:
        # keep track of the noobs
        noobs.append(user['noob'])

        if not user['specialities']:
            # user did not specify any specialities, so weigh down the specialities multiplier
            specialities_weight *= 1 - (1 / team_size)

        # count how many users have each speciality (for scoring later)
        for speciality in user['specialities']:
            specialities[speciality] += 1

    # make sure noobs are grouped together
    score = float(abs(noobs.count(True) - noobs.count(False)) * team_size)

    # prefer teams with diverse specialities
    score -= (max(specialities.values()) - min(specialities.values())) / len(SPECIALITIES) * team_size * specialities_weight

    # find friend balances (weight pretty hard on this one)
    for user1 in team:
        for user2 in team:
            # if both users want each other, weight this pretttttty hard!
            if user1['username'] in user2['team_requests'] and user2['username'] in user1['team_requests']:
                score += (team_size ** 2)
            # otherwise, weight it hard, but not as hard as it otherwise would be
            elif user1['username'] in user2['team_requests']: # only have to check this condition since it iterates over all users twice
                score += (team_size)

    return score


def get_optimized_teams(user_requests: dict) -> list:
    num_teams = math.ceil(len(user_requests) / TEAM_SIZE)
    __teams_list = [list() for x in range(num_teams)] # need new list() instances, can't use [[]]*num_teams!
    __user_requests = copy.deepcopy(user_requests) # we are going to make mods, so copy the dict

    if len(user_requests) <= TEAM_SIZE:
        return [user_requests]

    # make teams
    i = 0
    while __user_requests:
        user = random.choice(__user_requests)
        __teams_list[i % num_teams].append(user)
        __user_requests.remove(user)
        i += 1

    _teams = [ (team, score_team(team)) for team in __teams_list ]

    # for printing people on teams + score
    #[print(repr_team(team), score) for team, score in _teams]

    operations_since_last_change = 0
    while operations_since_last_change < len(_teams) * 20000: # TODO/XXX: hardcoded constant! :(
        # swap a couple random people
        team1_no = random.randint(0, num_teams - 1)
        
        while (team2_no := random.randint(0, num_teams - 1)) == team1_no:
            pass

        team1, last_team1_score = _teams[team1_no]
        team2, last_team2_score = _teams[team2_no]

        potential_team1 = team1.copy()
        potential_team2 = team2.copy()

        for i in range(random.randint(0, TEAM_SIZE-1)):
            person1_no = random.randint(0, len(potential_team1) - 1)
            person2_no = random.randint(0, len(potential_team2) - 1)

            person1 = potential_team1[person1_no]
            person2 = potential_team2[person2_no]

            potential_team1[person1_no] = person2
            potential_team2[person2_no] = person1

            # for debugging duplicate people on teams
            #assert not (len(set(repr_team(potential_team1))) < len(repr_team(potential_team1))), 'found the bug in team1 when swapping people with team1 ' + str(repr_team(team1)) + ' to potential_team1 ' + str(repr_team(potential_team1)) + ' (person1: %d, person2: %d)' % (person1_no, person2_no) + ' where team2 is ' + str(repr_team(team2))
            #assert not (len(set(repr_team(potential_team2))) < len(repr_team(potential_team2))), 'found the bug in team2 when swapping people with ' + str(repr_team(team2)) + ' to ' + str(repr_team(potential_team2)) + ' (person1: %d, person2: %d)' % (person1_no, person2_no)

        potential_team1_score = score_team(potential_team1)
        potential_team2_score = score_team(potential_team2)

        if (potential_team1_score > last_team1_score and potential_team2_score > last_team2_score) or (potential_team1_score > last_team1_score and potential_team2_score == last_team2_score) or (potential_team1_score == last_team1_score and potential_team2_score > last_team2_score):
            # for debugging what scores we impoved on
            # print('Swap', potential_team1_score, last_team1_score, '--', potential_team2_score, last_team2_score)

            # teams are better, so keep these
            _teams[team1_no] = (potential_team1, potential_team1_score)
            _teams[team2_no] = (potential_team2, potential_team2_score)

            operations_since_last_change = 0

        operations_since_last_change += 1

    return [ x[0] for x in _teams ]


if __name__ == '__main__':
    for team in get_optimized_teams(user_requests):
        print('Chose team', repr_team(team))
