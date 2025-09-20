import discord
from discord.ext import commands
import aiohttp
import json
import os
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import re

load_dotenv()

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

conversation_memory = {}

OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
with open("model.txt", "r", encoding="utf-8") as f:
    model = f.read()
MODEL_NAME = model

with open("prompt.txt", "r", encoding="utf-8") as f:
    prompt = f.read()
SYSTEM_PROMPT = prompt

# Config
CONFIG = {
    'timeout': 300,
    'stream_enabled': True,
    'max_response_length': 8000,
    'typing_update_interval': 5,  # Refresh typing status every 5 seconds
}
class ConversationManager:
    """Manage user's text history"""
    
    def __init__(self):
        self.conversations = {}
        self.max_history = 50
    
    def add_message(self, user_id, role, content):
        """Add conversations to memory"""
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        self.conversations[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Limit the length of text history
        if len(self.conversations[user_id]) > self.max_history * 2:
            self.conversations[user_id] = self.conversations[user_id][-self.max_history*2:]
    
    def get_context(self, user_id):
        """Fetch user's conversation history"""
        if user_id not in self.conversations:
            return []
        
        context = []
        for msg in self.conversations[user_id]:
            context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return context
    
    def clear_user_history(self, user_id):
        """Clean user's history"""
        if user_id in self.conversations:
            del self.conversations[user_id]

# Initialize conversation
conv_manager = ConversationManager()
def clean_response(text):
    """Remove thinking tags"""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text = re.sub(r'\[THINK\].*?\[/THINK\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Thinking\].*?\[/Thinking\]', '', text, flags=re.DOTALL)
    
    text = re.sub(r'```thinking.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'```think.*?```', '', text, flags=re.DOTALL)
    
    # Remove extra empty lines
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    text = text.strip()
    
    return text

async def keep_typing(channel):
    """Showing that the bot is keep typing"""
    try:
        while True:
            await channel.typing()
            await asyncio.sleep(CONFIG['typing_update_interval'])
    except asyncio.CancelledError:
        pass

async def query_ollama_stream(prompt, context, message):
    url = f"{OLLAMA_HOST}/api/chat"
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(context)
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "options": {"temperature":0.7, "top_p":0.9, "num_predict":4096}
    }

    sent_message = await message.reply("Thinking... ⏳")
    typing_task = asyncio.create_task(keep_typing(message.channel))
    
    try:
        timeout = aiohttp.ClientTimeout(total=CONFIG['timeout'])
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    typing_task.cancel()
                    await sent_message.edit(content=f"Error (Status code: {response.status})")
                    return f"Error (Status code: {response.status})"
                
                full_response = ""
                current_chunk = ""
                last_update_time = datetime.now()

                async for line in response.content:
                    if line:
                        try:
                            line_text = line.decode('utf-8').strip()
                            if not line_text:
                                continue
                            data = json.loads(line_text)
                            if 'message' in data and 'content' in data['message']:
                                chunk = data['message']['content']
                                full_response += chunk
                                current_chunk += chunk

                                now = datetime.now()
                                time_diff = (now - last_update_time).total_seconds()

                                if len(current_chunk) > 500 or (time_diff > 3 and len(current_chunk) > 50):
                                    cleaned_partial = clean_response(full_response)
                                    await sent_message.edit(content=cleaned_partial + " ⏳")
                                    current_chunk = ""
                                    last_update_time = now

                                if data.get('done', False):
                                    break
                        except:
                            continue

                # Send full response
                typing_task.cancel()
                cleaned_response = clean_response(full_response)
                if not cleaned_response:
                    cleaned_response = "Sorry, I cannot generate a valid response."
                
                await sent_message.edit(content=cleaned_response)
                return cleaned_response

    except asyncio.TimeoutError:
        typing_task.cancel()
        await sent_message.edit(content="⚠️ Timeout, please try later.")
        return "Timeout"
    except Exception as e:
        typing_task.cancel()
        await sent_message.edit(content=f"❌ ERROR：{str(e)}")
        return f"ERROR：{str(e)}"

async def query_ollama(prompt, context, message=None):
    """Send request to Ollama API（Non-streaming mode）"""
    url = f"{OLLAMA_HOST}/api/chat"
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    messages.extend(context)
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 4096,
        }
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=CONFIG['timeout'])
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if message:
                processing_msg = await message.reply("🤔 Processing with your message, it may take some seconds...")
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    raw_response = data.get('message', {}).get('content', 'Sorry, I cannot generate a response.')
                    cleaned_response = clean_response(raw_response)
                    
                    if message and 'processing_msg' in locals():
                        try:
                            await processing_msg.delete()
                        except:
                            pass
                    
                    return cleaned_response if cleaned_response else 'Sorry, I cannot generate a valid response.'
                else:
                    print(f"Ollama API error: {response.status}")
                    if message and 'processing_msg' in locals():
                        try:
                            await processing_msg.delete()
                        except:
                            pass
                    return "Sorry, AI service is currently unavailable."
                    
    except asyncio.TimeoutError:
        if message and 'processing_msg' in locals():
            try:
                await processing_msg.edit(content="⚠️ It may take more time to process with your message, you may simplify your message after it.")
            except:
                pass
        return "The processing time is too long. Please simplify your message."
    except Exception as e:
        print(f"Error occured when connecting to Ollama: {e}")
        return f"Cannot connect to AI service：{str(e)}"
@bot.event
async def on_ready():
    """Send the messages when the bot is activated."""
    print(f'{bot.user} is now online!')
    print(f'Connected {len(bot.guilds)} server(s)')
    print(f'Using model: {MODEL_NAME}')
    print(f'Timeout: {CONFIG["timeout"]} seconds')
    print(f'Streaming mode: {"Enabled" if CONFIG["stream_enabled"] else "Disabled"}')
    
    test_response = await query_ollama("Connection test", [], None)
    if "Sorry" not in test_response and "error" not in test_response:
        print("✓ Ollama connected")
    else:
        print("✗ Cannot connect to Ollama. Please check if Ollama is running")
@bot.event
async def on_message(message):
    """Message events"""
    # Avoid replying to itself
    if message.author == bot.user:
        return
    
    # Check if mentioned
    if bot.user.mentioned_in(message):
        # Remove tag
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        # Show hints if there is no content
        if not content:
            await message.reply("Please provide your message.")
            return
        
        user_id = str(message.author.id)
        
        # Clear memory
        if content.lower() in ["清除記憶", "clear memory", "reset"]:
            conv_manager.clear_user_history(user_id)
            await message.reply("Memory cleared.")
            return
        
        # Check memory status
        if content.lower() in ["記憶狀態", "memory status", "status"]:
            count = len(conv_manager.conversations.get(user_id, []))
            await message.reply(f"Now storing {count} message records.")
            return
        
        # Show prompt
        if content.lower() in ["系統提示", "system prompt", "prompt"]:
            prompt_preview = SYSTEM_PROMPT[:500] + "..." if len(SYSTEM_PROMPT) > 500 else SYSTEM_PROMPT
            embed = discord.Embed(
                title="Prompt",
                description=f"```{prompt_preview}```",
                color=discord.Color.blue()
            )
            await message.reply(embed=embed)
            return
        
        # Switch mode
        if content.lower() in ["串流模式", "stream mode"]:
            CONFIG['stream_enabled'] = not CONFIG['stream_enabled']
            status = "enabled" if CONFIG['stream_enabled'] else "disabled"
            await message.reply(f"Streaming mode is now {status}")
            return
        
        try:
            # Fetch message history
            context = conv_manager.get_context(user_id)
            
            # Choose how to query according to the settings
            if CONFIG['stream_enabled']:
                response = await query_ollama_stream(content, context, message)
            else:
                async with message.channel.typing():
                    response = await query_ollama(content, context, message)
                
                # Send response
                if len(response) > 2000:
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            await message.reply(chunk)
                        else:
                            await message.channel.send(chunk)
                else:
                    await message.reply(response)
            
            conv_manager.add_message(user_id, "user", content)
            conv_manager.add_message(user_id, "assistant", response)
            
        except Exception as e:
            print(f"Error occured when processing your message: {e}")
            await message.reply(f"Error occured when processing your message: {str(e)}")
    
    # Other commands
    await bot.process_commands(message)
@bot.command(name='ping')
async def ping(ctx):
    """Ping Pong"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'Pong! Delay: {latency}ms')

@bot.command(name='model')
async def model_info(ctx):
    """Show model being used"""
    await ctx.send(f'Now using: {MODEL_NAME}')

@bot.command(name='config')
async def show_config(ctx):
    """Show config"""
    embed = discord.Embed(
        title="Bot Config",
        color=discord.Color.blue()
    )
    embed.add_field(name="Model", value=MODEL_NAME, inline=True)
    embed.add_field(name="Timeout", value=f"{CONFIG['timeout']} seconds", inline=True)
    embed.add_field(name="Streaming mode", value="Enabled" if CONFIG['stream_enabled'] else "Disabled", inline=True)
    embed.add_field(name="Maximum response length", value=f"{CONFIG['max_response_length']} characters", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='timeout')
@commands.has_permissions(administrator=True)
async def set_timeout(ctx, seconds: int):
    """Set timeout (Admin roles needed)"""
    if seconds < 10 or seconds > 600:
        await ctx.send("Timeout must be between 10 to 600")
        return
    
    CONFIG['timeout'] = seconds
    await ctx.send(f"Timeout is set to {seconds} seconds")

@bot.command(name='set_prompt')
@commands.has_permissions(administrator=True)
async def set_prompt(ctx, *, new_prompt):
    """Set prompt (Admin roles needed)"""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = new_prompt
    
    embed = discord.Embed(
        title="Prompt is updated",
        description=f"New prompt length: {len(new_prompt)} characters",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='help_ai')
async def help_ai(ctx):
    """Show help message"""
    help_text = """
    **How to use**
    
    **Basic:**
    • @bot [Your message] - Chat with the bot
    
    **Special commands:**
    • @bot Clear memory - Clear your conversation history
    • @bot Memory status - Check the number of messages in memory
    • @bot System prompt - Check the prompt being used
    • @bot Stream mode - Switch between stream mode and non-stream mode
    
    **Management commands:**
    • !ping - Test delay time
    • !model - Check the model being used
    • !config - Check config
    • !timeout [seconds] - Set timeout（Admin needed）
    • !set_prompt [new prompt] - Set new system prompt（Admin needed）
    • !help_ai - Show this help message
    """
    embed = discord.Embed(
        title="Help",
        description=help_text,
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Error tackling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have the permission to execute this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument(s).")
    else:
        print(f'Error: {error}')
        await ctx.send(f"❌ Error occured: {str(error)}")
def main():
    """Main function"""
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: Discord token not found! Please check .env file.")
        return
    
    print("="*50)
    print("Starting Discord AI Bot...")
    print("="*50)
    print(f"Model: {MODEL_NAME}")
    print(f"Timeout: {CONFIG['timeout']} seconds")
    print(f"Streaming mode: {'Enabled' if CONFIG['stream_enabled'] else 'Disabled'}")
    print(f"System prompt length: {len(SYSTEM_PROMPT)} characters")
    print("="*50)
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("Error! Invalid Discord Token!")
    except Exception as e:
        print(f"Error occured: {e}")
if __name__ == "__main__":
    main()
