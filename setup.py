from setuptools import setup, find_packages

setup(
    name='fastlimiter',
    version='0.1.0',
    description='A fast token bucket rate limiter',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Anthony Therrien',
    url='https://github.com/anto18671/fastlimiter',
    license='MIT',
    packages=find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=[
        'fastapi>=0.65.0',
    ],
    extras_require={
        'dev': [
            'uvicorn>=0.30.6',
            'httpx>=0.27.2',
            'pytest>=8.3.3',
            'pytest_asyncio>=0.24.0'
        ],
    },
    python_requires='>=3.8',
    keywords='rate-limiter, token-bucket, fastapi, middleware',
    project_urls={
        'Bug Tracker': 'https://github.com/anto18671/fastlimiter/issues',
        'Source Code': 'https://github.com/anto18671/fastlimiter',
    },
)
