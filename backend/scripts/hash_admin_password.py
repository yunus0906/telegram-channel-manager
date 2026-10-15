"""Create an Argon2 password hash without echoing the password."""
from getpass import getpass

from argon2 import PasswordHasher


first = getpass("管理员密码: ")
second = getpass("再次输入: ")
if len(first) < 12:
    raise SystemExit("密码至少需要 12 个字符")
if first != second:
    raise SystemExit("两次输入不一致")
print(PasswordHasher().hash(first))
