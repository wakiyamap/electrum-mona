from pythonforandroid.recipe import PythonRecipe
from pythonforandroid.util import HashPinnedDependency

assert PythonRecipe.depends == ['python3']
assert PythonRecipe.python_depends == []


class Lyra2re2HashRecipe(PythonRecipe):
    # C extension for the Lyra2REv2 proof-of-work of Monacoin. (p4a has no built-in recipe for it)
    version = "1.2.0"
    # note: this version is duplicated in contrib/deterministic-build/requirements.txt
    #       and in contrib/build-wine/build-lyra2rev2.sh
    sha512sum = "940cb48a2114d56b09499d6488a568c5672d92cf656a63ecf11738b09210a3a7c29620f5378a747d970800d3db5e1dfc329a1edaa252ae807361d1e781e1eed7"
    url = "https://files.pythonhosted.org/packages/source/l/lyra2re2_hash/lyra2re2_hash-{version}.tar.gz"
    hostpython_prerequisites = [
        HashPinnedDependency(package="setuptools==80.9.0",
                             hashes=['sha256:062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922']),
    ]
    call_hostpython_via_targetpython = False

    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super().get_recipe_env(arch, with_flags_in_cc)
        # - "-fno-strict-aliasing": the C sources break strict-aliasing rules, and without this
        #   they can get miscompiled (the module then returns wrong hashes)
        # - "-DPY_SSIZE_T_CLEAN": needed on python < 3.13, as "y#" is used with Py_BuildValue
        # (same flags as LYRA2RE2_HASH_CFLAGS in contrib/build_tools_util.sh)
        env['CFLAGS'] += ' -fno-strict-aliasing -DPY_SSIZE_T_CLEAN'
        return env


recipe = Lyra2re2HashRecipe()
