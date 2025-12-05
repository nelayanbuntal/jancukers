"""
Script untuk update import database ke database_supabase
Jalankan: python update_imports.py
"""

import os
import re
from pathlib import Path

# Files yang perlu diupdate
FILES_TO_UPDATE = [
    'bot.py',
    'webhook_server.py',
    'admin_commands.py'  # jika ada
]

# Pattern untuk mencari import database
OLD_IMPORT_PATTERN = r'from database import'
NEW_IMPORT_PATTERN = 'from database_supabase import'

def backup_file(filepath):
    """Backup file sebelum dimodifikasi"""
    backup_path = f"{filepath}.backup"
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_path}")
        return True
    return False

def update_imports_in_file(filepath):
    """Update import statements dalam file"""
    if not os.path.exists(filepath):
        print(f"⚠️ File not found: {filepath}")
        return False
    
    print(f"\n📝 Processing: {filepath}")
    
    # Backup dulu
    backup_file(filepath)
    
    # Read file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already using database_supabase
    if 'from database_supabase import' in content:
        print(f"   ℹ️ Already using database_supabase - skipping")
        return True
    
    # Count occurrences
    old_count = content.count('from database import')
    
    if old_count == 0:
        print(f"   ℹ️ No database imports found - skipping")
        return True
    
    # Replace imports
    new_content = re.sub(
        OLD_IMPORT_PATTERN,
        NEW_IMPORT_PATTERN,
        content
    )
    
    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"   ✅ Updated {old_count} import statement(s)")
    return True

def show_diff_preview(filepath):
    """Show preview of changes"""
    if not os.path.exists(filepath):
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if 'from database import' in line:
                print(f"   Line {line_num}: {line.strip()}")
                print(f"   Will become: {line.replace('from database import', 'from database_supabase import').strip()}")

def main():
    """Main function"""
    print("=" * 60)
    print("🔄 DATABASE IMPORT UPDATER")
    print("=" * 60)
    print("\nThis script will update all database imports to use Supabase.")
    print("\n⚠️ IMPORTANT:")
    print("  - Backup files will be created (.backup)")
    print("  - Make sure you have database_supabase.py in your directory")
    print("  - Review changes before running your bot")
    
    # Check if database_supabase.py exists
    if not os.path.exists('database_supabase.py'):
        print("\n❌ ERROR: database_supabase.py not found!")
        print("   Please create this file first before running this script.")
        return
    
    print("\n" + "=" * 60)
    print("PREVIEW OF CHANGES:")
    print("=" * 60)
    
    # Show preview
    for filepath in FILES_TO_UPDATE:
        if os.path.exists(filepath):
            print(f"\n📄 {filepath}:")
            show_diff_preview(filepath)
    
    # Ask for confirmation
    print("\n" + "=" * 60)
    response = input("\nProceed with updates? (yes/no): ").strip().lower()
    
    if response not in ['yes', 'y']:
        print("\n❌ Operation cancelled by user")
        return
    
    # Update files
    print("\n" + "=" * 60)
    print("UPDATING FILES:")
    print("=" * 60)
    
    success_count = 0
    for filepath in FILES_TO_UPDATE:
        if update_imports_in_file(filepath):
            success_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ UPDATE COMPLETE!")
    print("=" * 60)
    print(f"\nFiles updated: {success_count}/{len(FILES_TO_UPDATE)}")
    print("\n📋 Next steps:")
    print("1. Review the changes in each file")
    print("2. Update your .env file with Supabase credentials")
    print("3. Run: python test_supabase.py")
    print("4. Run: python bot.py")
    print("\n💡 Tip: If something goes wrong, restore from .backup files")
    
    # Create rollback script
    create_rollback_script()

def create_rollback_script():
    """Create script to rollback changes"""
    rollback_content = """#!/usr/bin/env python3
\"\"\"
Rollback script - restore from backup files
\"\"\"
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

print("\\n✅ Rollback complete!")
"""
    
    with open('rollback.py', 'w', encoding='utf-8') as f:
        f.write(rollback_content)
    
    print("\n💾 Rollback script created: rollback.py")
    print("   Run 'python rollback.py' if you need to undo changes")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()