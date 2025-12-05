#!/usr/bin/env python3
"""
Rollback script - restore from backup files
"""
import os
import shutil

files = ['bot.py', 'webhook_server.py', 'admin_commands.py']

for f in files:
    backup = f + '.backup'
    if os.path.exists(backup):
        shutil.copy(backup, f)
        print(f"✅ Restored: {f}")
    else:
        print(f"⚠️ No backup found: {backup}")

print("\n✅ Rollback complete!")
