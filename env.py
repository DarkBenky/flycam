import os
from dotenv import load_dotenv

load_dotenv()
SECRET         = os.getenv("SECRET")
GO_SERVER      = os.getenv("GO_SERVER")
GO_META_SERVER = os.getenv("GO_META_SERVER")