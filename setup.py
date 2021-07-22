"""Setup"""
import os
from setuptools import setup, find_packages

# figure out the version
about = {}
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "synapseformation", "__version__.py")) as f:
    exec(f.read(), about)

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='synapseformation',
    version=about["__version__"],
    description='Client for using Synapse Formation templates.',
    url='https://github.com/Sage-Bionetworks/synapseformation',
    author='Kenneth Daily,Thomas Yu,Kelsey Montgomery',
    license='Apache',
    packages=find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    zip_safe=False,
    python_requires='>=3.6',
    entry_points={'console_scripts': ['synapseformation = synapseformation.__main__:cli']},
    install_requires=['click',
                      'synapseclient>=2.4.0',
                      'pyyaml'],
    project_urls={
        "Documentation": "https://github.com/Sage-Bionetworks/synapseformation",
        "Source Code": "https://github.com/Sage-Bionetworks/synapseformation",
        "Bug Tracker": "https://github.com/Sage-Bionetworks/synapseformation/issues",
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Operating System :: MacOS',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: Unix',
        'Operating System :: POSIX :: Linux',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Software Development :: Libraries',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Bio-Informatics'
    ],
)
