"""Setup"""
import os
from setuptools import setup, find_packages

# figure out the version
about = {}
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "synapseformation", "__version__.py")) as f:
    exec(f.read(), about)

setup(name='synapseformation',
      version=about["__version__"],
      description='Client for using Synapse Formation templates.',
      url='https://github.com/Sage-Bionetworks/synapseformation',
      author='Kenneth Daily,Thomas Yu,Kelsey Montgomery',
      license='Apache',
      packages=find_packages(),
      zip_safe=False,
      python_requires='>=3.6',
      entry_points={'console_scripts': ['synapseformation = synapseformation.__main__:cli']},
      install_requires=['click',
                        'synapseclient>=1.9.4'])
