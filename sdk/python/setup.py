from setuptools import setup

setup(
    name="ward_protocol",
    version="0.1.0",
    description="Official Python SDK for Ward Protocol - XRPL AMM DeFi",
    long_description=open("README.md").read() if open("README.md") else "",
    long_description_content_type="text/markdown",
    author="Ward Protocol Team",
    url="https://github.com/ward-protocol",
    packages=["ward_protocol"],
    package_dir={"ward_protocol": "."},
    install_requires=[
        "httpx>=0.25.0",
        "pydantic>=2.5.0",
    ],
    python_requires=">=3.10",
    include_package_data=True,
)
