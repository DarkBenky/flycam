from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

ext = Extension(
    "quant",
    sources=["quant.pyx"],
    include_dirs=[np.get_include()],
    extra_compile_args=["-O3", "-march=native", "-ffast-math"],
)

setup(
    ext_modules=cythonize(
        ext,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
            "nonecheck": False,
            "initializedcheck": False,
        }
    )
)
