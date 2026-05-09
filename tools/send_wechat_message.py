#!/usr/bin/env python3
import sys
import subprocess
import argparse


def send_wechat_message(contact_name: str, message: str) -> bool:
    applescript = f'''
    tell application "WeChat"
        set targetChat to missing value
        repeat with chat in chats
            if name of chat is "{contact_name}" then
                set targetChat to chat
                exit repeat
            end if
        end repeat
        
        if targetChat is not missing value then
            send "{message}" to targetChat
            return true
        else
            return false
        end if
    end tell
    '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', applescript],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip() == 'true':
            return True
        else:
            return False
    except subprocess.TimeoutExpired:
        print("Error: Operation timed out")
        return False
    except Exception as e:
        print(f"Error: {str(e)}")