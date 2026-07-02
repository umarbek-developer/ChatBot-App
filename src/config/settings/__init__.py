import os
import environ

env = environ.Env()

BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = int(os.environ.get("DEBUG", 1))

if DEBUG:
    print("DEBUG: ", DEBUG)
    print("Development settings")
    from .development import *
else:
    print("production settings start")
    from .production import *

