import setuptools

VERSION = "1.3.7"

with open('README.md') as file:
    long_description = file.read()

REQUIREMENTS = ['pystripe']


CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Programming Language :: Python :: 3.7',
]

# calling the setup function 
setuptools.setup(name='destripegui',
      version=VERSION,
      description='A GUI for automatic pystripe destriping',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='https://github.com/lifecanvastechnologies',
      author='LifeCanvas Technologies',
      license='MIT',
      packages=setuptools.find_packages(),
      include_package_data=True,
      package_data={'': ['data/config.ini', 'data/lct.ico']},
      classifiers=CLASSIFIERS,
      install_requires=REQUIREMENTS,
      entry_points={
        'console_scripts' : ['destripegui=destripegui.destripegui:main']
      }
)
