from setuptools import setup

VERSION = "1.0.0"

with open('README.md') as file:
    long_description = file.read()

REQUIREMENTS = ['pystripe', 'os', 'multiprocessing', 'configparser', 'pathlib', 'csv', 'tkinter', 'sys']


# some more details
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Programming Language :: Python :: 3.7',
]

# calling the setup function 
setup(name='destripegui',
      version=VERSION,
      description='A GUI for automatic pystripe destriping',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/nikhilkumarsingh/mygmap',
      author='LifeCanvas Technologies',
      license='MIT',
      packages=['pystripe'],
      classifiers=CLASSIFIERS,
      install_requires=REQUIREMENTS,
      entry_points={
        'console_scripts' : ['destripegui=src.destripegui:main']
      }
)
