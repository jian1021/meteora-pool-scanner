"""确保测试可以将项目根目录加入 import 路径。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
