#!/usr/bin/env python3

import discord
from discord.ext import commands

import yaml
import logging


client = discord.Client()
bot = commands.Bot(command_prefix='!')

config = dict()


##########


_user_cache = dict()
def resolve_user(ctx, user: str, use_cache: bool=False) -> discord.Member:
    assert isinstance(user, str)

    converter = MemberConverter() # XXX: should I move this to the global scope?
    member = _user_cache.get(user)
    if (not use_cache) or not member:
        member = await converter.convert(ctx, user)
        _user_cache[user] = member

    return member


##########


@client.event
async def on_ready():
    logging.info(f'{client.user} has connected to Discord!')
    #await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='to your requests'))


@client.event
async def on_reaction_add(reaction, member):
    if reaction.message.id == config['specializations']['message-id']:
        name = reaction.emoji.name
        try:
            tag = config['specializations']['emojis'].get(name)
            if not tag:
                reaction.message.remove_reaction(reaction.emoji, member)
                assert tag, f'Emoji "{name}" is meaningless'
        except Exception as e:
            logging.error('when adding reaction: ' + str(e))


@bot.command(pass_context=True)
async def request(ctx, *args):
    # don't actually do anything with the users we find here;
    # we do all of the hard work once the event starts. For now, just check to 
    # make sure all of the users exist
    _users_not_found = list()
    for username in set(args):
        # the work usually won't be wasted since it's stored in cache
        if not resolve_user(ctx, username):
            _users_not_found.append(username)

    if _users_not_found:
        # TODO: send message saying the users weren't found. don't forget to
        # sanitize the usernames
        pass
    else:
        # TODO: add a check mark reaction to the message. search for previous
        # commands, and drop the old check mark if exists.
        pass

##########


if __name__ == '__main__':
    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f.read())
        token = config.get('discord', {}).get('token')
        assert token, 'Config is missing discord.token'

    client.run(token)
