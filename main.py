#!/usr/bin/env python3

import discord
import discord.ext.commands

import typing
import yaml
import logging
import unicodedata

import db
import team


intents = discord.Intents.default()
intents.reactions = True
intents.members = True
client = discord.ext.commands.Bot(command_prefix='!', intents=intents)

config = dict()
msg_settings = {'allowed_mentions': discord.AllowedMentions(everyone=False, roles=set())}


##########


_user_cache = dict()
'''
resolves a username to a discord.member.Member object
'''
async def resolve_user(ctx: discord.ext.commands.context.Context, user: str, use_cache: bool=False) -> discord.member.Member:
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


'''
creates a set of discord.member.Member who are competitors
'''
async def get_competitors(ctx: discord.ext.commands.context.Context) -> typing.Set[discord.member.Member]:
    competitors = set(ctx.guild.members)
    for role_name in config['discord']['ignore-roles']:
        competitors -= set(discord.utils.get(ctx.guild.roles, name=role_name).members)

    return competitors


'''
get the db users dict for the Member object
'''
def _get_db_user_from_user(user: discord.member.Member) -> dict:
    uid = str(user)

    assert 'users' in db.db
    if uid not in db.db['users']:
        db.db['users'][uid] = dict()
        db.write()

    return db.db['users'][uid]


'''
get the db users dict for the user who executed a command based on ctx
'''
def _get_db_user_from_ctx(ctx: discord.ext.commands.context.Context) -> dict:
    assert ctx
    return _get_db_user_from_user(ctx.author)


'''
a hack to assign names to emojis so that we can use them in config files 
without needing to type unicode emojis
'''
def _emoji_to_name(emoji: str) -> str:
    return unicodedata.name(emoji).lower().replace(' ', '_').replace('symbol_letter_', '')


##########


@client.event
async def on_ready() -> None:
    logging.info(f'{client.user} has connected to Discord!')
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='your requests'))


@client.event
async def on_raw_reaction_add(payload: discord.raw_models.RawReactionActionEvent) -> None:
    if payload.message_id == config['discord']['specializations']['message-id']:
        channel = await client.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = await client.fetch_user(payload.user_id)
        emoji = payload.emoji

        name = _emoji_to_name(emoji.name)
        try:
            tag = config['discord']['specializations']['emojis'].get(name)
            if not tag:
                print(f'Removing meaningless emoji "{name}" ({emoji.name})')
                await message.remove_reaction(emoji, payload.member)
        except Exception as e:
            logging.error('when adding reaction: ' + str(e))


##########


@client.command(pass_context=True)
async def request(ctx: discord.ext.commands.context.Context, *args) -> None:
    if ctx.channel.id == config['discord']['team-requests']['channel-id']:
        _users_not_found = list()
        _users_found = list()
        for username in set(args):
            # the work usually won't be wasted since it's stored in cache
            if not (user := await resolve_user(ctx, username)):
                _users_not_found.append(username)
            else:
                # TODO: check to make sure both requested&requesting user have the right role
                _users_found.append(str(user))
                pass

        if _users_found:
            _get_db_user_from_ctx(ctx)['team_requests'] = _users_found
            db.write()


        if _users_not_found:
            # send message saying the users weren't found. 
            msg = '**Warning:** Unable to find users: `' + '`, `'.join(_users_not_found) + '`'
            await ctx.send(msg, **msg_settings)
        else:
            # TODO: search for previous commands, and drop the old check mark if exists.
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


MAKETEAMS_LOCK = False
@client.command(pass_context=True)
async def maketeams(ctx: discord.ext.commands.context.Context, *args) -> None:
    global MAKETEAMS_LOCK

    if MAKETEAMS_LOCK:
        await ctx.send('Team generation already in progress, ignoring additional request...')
        return

    MAKETEAMS_LOCK = True

    if ctx.channel.id == config['discord']['maketeams']['channel-id']:
        channel = ctx.guild.get_channel(int(config['discord']['specializations']['channel-id']))
        msg = await channel.fetch_message(int(config['discord']['specializations']['message-id']))

        # reset specialities
        for username in db.db['users']:
            if 'specialities' in db.db['users'][username]:
                del db.db['users'][username]['specialities']

        # parse reactions => specialities
        print('Parsing reactions...')
        for reaction in msg.reactions:
            emoji_name = _emoji_to_name(reaction.emoji)

            # if the emoji is meaningless, skip it
            if not (speciality := config['discord']['specializations']['emojis'].get(emoji_name)):
                continue

            async for user in reaction.users(limit=None, after=None):
                user_dict = _get_db_user_from_user(user)
                if 'specialities' not in user_dict:
                    user_dict['specialities'] = list()

                user_dict['specialities'].append(speciality)
                db.write()

        await ctx.send('Generating optimized teams, please wait (this may take a few minutes)...')
        print(db.db)
        # TODO be sure to & with the set get_competitors()
    else:
        await ctx.send('Wrong channel.') # we use message send permission in channels for access control

    MAKETEAMS_LOCK = False


@client.command(pass_context=True)
async def ping(ctx: discord.ext.commands.context.Context) -> None:
    await ctx.send('Pong! I am alive.', **msg_settings)


##########


if __name__ == '__main__':
    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f.read())
        token = config.get('discord', {}).get('token')
        assert token, 'Config is missing discord.token'

    db.read()

    client.run(token)
