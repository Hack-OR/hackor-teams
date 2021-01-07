#!/usr/bin/env python3

import discord
import discord.ext.commands

import yaml
import logging
import unicodedata


intents = discord.Intents.default()
intents.reactions = True
intents.members = True
client = discord.ext.commands.Bot(command_prefix='!', intents=intents)

config = dict()
msg_settings = {'allowed_mentions': discord.AllowedMentions(everyone=False, roles=set())}


##########


_user_cache = dict()
async def resolve_user(ctx, user: str, use_cache: bool=False) -> discord.Member:
    assert isinstance(user, str)

    converter = discord.ext.commands.MemberConverter() # XXX: should I move this to the global scope?
    member = _user_cache.get(user)
    if (not use_cache) or not member:
        try:
            member = await converter.convert(ctx, user)
        except discord.ext.commands.errors.MemberNotFound:
            member = None

        if (not member) and user.startswith('@'):
            member = await resolve_user(ctx, user[1:], use_cache=use_cache)

        if member:
            _user_cache[user] = member

    return member


async def get_competitors(ctx) -> set:
    competitors = set(ctx.guild.members)
    for role_name in config['discord']['ignore-roles']:
        competitors -= set(discord.utils.get(ctx.guild.roles, name=role_name).members)

    return competitors


##########


@client.event
async def on_ready():
    logging.info(f'{client.user} has connected to Discord!')
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='your requests'))


@client.event
async def on_raw_reaction_add(payload):
    if payload.message_id == config['discord']['specializations']['message-id']:
        channel = await client.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = await client.fetch_user(payload.user_id)
        emoji = payload.emoji

        name = unicodedata.name(emoji.name).lower().replace(' ', '_').replace('symbol_letter_', '') # XXX: hack to name emoji
        try:
            tag = config['discord']['specializations']['emojis'].get(name)
            if not tag:
                print(f'Removing meaningless emoji "{name}" ({emoji.name})')
                await message.remove_reaction(emoji, payload.member)
        except Exception as e:
            logging.error('when adding reaction: ' + str(e))


@client.command(pass_context=True)
async def request(ctx, *args):

    if ctx.channel.id == config['discord']['team-requests']['channel-id']:
        # don't actually do anything with the users we find here;
        # we do all of the hard work once the event starts. For now, just check to 
        # make sure all of the users exist
        _users_not_found = list()
        for username in set(args):
            # the work usually won't be wasted since it's stored in cache
            if not (user := await resolve_user(ctx, username)):
                _users_not_found.append(username)
            else:
                # check to make sure the user has the right role
                pass

        if _users_not_found:
            # send message saying the users weren't found. 
            msg = '**Warning:** Unable to find users: `' + '`, `'.join(_users_not_found) + '`'
            await ctx.send(msg, **msg_settings)
        else:
            # TODO: search for previous commands, and drop the old check mark if exists.
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


@client.command(pass_context=True)
async def ping(ctx):
    await ctx.send('Pong! I am alive.', **msg_settings)


##########


if __name__ == '__main__':
    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f.read())
        token = config.get('discord', {}).get('token')
        assert token, 'Config is missing discord.token'

    client.run(token)
