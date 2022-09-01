# GoCD Configuration Repository - LabVIEW PPLs

## Introduction

This repository contains both the `*.gocd.yaml` files, which provide a
definition of pipelines to be used on a GoCD server to build a series
of Packed Project Libraries with LabVIEW in Docker containers, and also
the python code (`scripts/*`) to generate those files.

It also contains a Dockerfile and simple Python file to run a webservice
that provides a mutex - this is necessary for the NIPKG publication from
Docker containers (because `nipkg feed-add-pkg` is not threadsafe).

## How to adapt to your own use

It is not expected that the .gocd.yaml files are particularly useful,
except as a reference guide for how such files can be structured.\
More information about the valid syntax can be found directly at the
repository for the plugin which processes the configurations: 
[gocd-yaml-config-plugin](https://github.com/tomzo/gocd-yaml-config-plugin).

Instead, this repository is published with the hope that the Python
scripts can be useful in generating a configuration file that suits your
build steps and repositories.

There is no requirement to use Python to generate such a `.gocd.yaml` file - 
but it was chosen here as a widespread language with a reportedly easy-to-understand
structure and syntax. You could use whatever language you liked (including,
of course, LabVIEW).

## Comments on the YamlGenerator.py, Constants.py and Generate_PPL_Pipelines.py files

Within the `YamlGenerator.py` and `Constants.py` files, there are many 
variables defined for the purpose of generating
[YAML aliases](https://github.com/tomzo/gocd-yaml-config-plugin#yaml-aliases),
in order to reduce the output file size.\
This sometimes makes the code seem excessively fragmented, when a function
could be used to generate the same output more tidily (and with a function
name that provided self-documenting code).\
However, use of a function provides a new object on each run, and then the
aliases are not created (comparison is by reference/id, not content).\
Hopefully splitting the majority of the constants into a separate file eases
the reading of the YamlGenerator.py file.

`Generate_PPL_Pipelines.py` is the file which should be executed using Python
to generate the `LabVIEW_PPL-Pipelines.gocd.yaml` file.\
It clones a list of repositories (in `repoList.txt`) and then searches for
the libraries named in that file within the repository that is cloned.\
It also parses a `<libraryName>.mk` file to build a list of dependencies.
This allows the repository containing a library to declare on what it depends,
rather than needing a global declaration of dependencies. Nested dependencies
are automatically detected and scheduled appropriately by GoCD.