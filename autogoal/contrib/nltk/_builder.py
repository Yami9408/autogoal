import gensim
import nltk
import black

import textwrap
import datetime
import inspect
import re
import numpy as np
import warnings
import abc
import importlib
import enlighten


from pathlib import Path
from autogoal.kb import *
from autogoal.grammar import Discrete, Continuous, Categorical, Boolean
from autogoal.contrib.sklearn._builder import SklearnWrapper
from ._utils import _is_algorithm, get_input_output, is_algorithm

languages = [
    "arabic",
    "danish",
    "dutch",
    "english",
    "finnish",
    "french",
    "german",
    "hungarian",
    "italian",
    "norwegian",
    "portuguese",
    "romanian",
    "russian",
    "spanish",
    "swedish",
]

languages_re = re.compile("|".join(languages))

class NltkTokenizer(SklearnWrapper):
    def _train(self, input):
        return self.tokenize(input)


    def _eval(self, input):
        return self.tokenize(input)

    @abc.abstractmethod
    def tokenize(self, X, y=None):
        pass

class NltkStemmer(SklearnWrapper):
    def _train(self, input):
        #input is Word
        return self.stem(input)

    def _eval(self, input):
        #input is Word
        return self.stem(input)

    @abc.abstractmethod
    def stem(self, X, y=None):
        pass

class NltkLemmatizer(SklearnWrapper):
    def _train(self, input):
        return self.lemmatize(input)

    def _eval(self, input):
        return self.lemmatize(input)

    @abc.abstractmethod
    def lemmatize(self, X, y=None):
        pass

class NltkClusterer(SklearnWrapper):
    def _train(self, input):
        X, y = input
        self.cluster(X)
        return X, y

    def _eval(self, input):
        X, y = input
        return X, [self.classify(x) for x in X]

    @abc.abstractmethod
    def cluster(self, X, y=None):
        pass

    @abc.abstractmethod
    def classify(self, X, y=None):
        pass

class NltkClassifier(SklearnWrapper):
    def _train(self, input):
        X, y = input
        self.train(X) #TODO: fix train incompability for nltk classifiers
        return X, y

    def _eval(self, input):
        X, y = input
        return X, [self.classify(x) for x in X]

    @abc.abstractmethod
    def cluster(self, X, y=None):
        pass

    @abc.abstractmethod
    def classify(self, X, y=None):
        pass

base_classes = {"classifier":"NltkClassifier",
                "clusterer":"NltkClusterer",
                "sent_tokenizer":"NltkTokenizer",
                "word_tokenizer":"NltkTokenizer",
                "lemmatizer":"NltkLemmatizer",
                "stemmer":"NltkStemmer",
                "word_embbeder":"SklearnWrapper",
                "doc_embbeder":"SklearnWrapper"}

GENERATION_RULES = dict(
    SnowballStemmer = dict(
        assume = True,
        assume_input=Word(),
        assume_output=Stem()
    ),
)


def build_nltk_wrappers():
    imports = _walk(nltk)
    imports += _walk(nltk.cluster)
    imports += _walk(gensim.models)

    manager = enlighten.get_manager()
    counter = manager.counter(total=len(imports), unit="classes")
    path = Path(__file__).parent / "_generated.py"

    with open(path, "w") as fp:
        fp.write(
            textwrap.dedent(f"""
            # AUTOGENERATED ON {datetime.datetime.now()}
            ## DO NOT MODIFY THIS FILE MANUALLY

            from autogoal.grammar import Continuous, Discrete, Categorical, Boolean
            from autogoal.contrib.nltk._builder import NltkStemmer, NltkTokenizer, NltkLemmatizer, NltkClusterer
            from autogoal.kb._data import *
            from autogoal.utils import nice_repr
            from numpy import inf, nan
            """
            )
        )

        for cls in imports:
            counter.update()
            _write_class(cls, fp)

    black.reformat_one(path, True, black.WriteBack.YES, black.FileMode(), black.Report())

    counter.close()
    manager.stop()

def _write_class(cls, fp):
    try:
        args = _get_args(cls)
    except Exception as e:
        warnings.warn("Error to generate wrapper for %s : %s" % (cls.__name__, e))
        return

    rules = GENERATION_RULES.get(cls.__name__)
    assumed = False

    if rules:
        if rules.get("assume"):
            assumed = True
            inputs = rules.get("assume_input")
            outputs = rules.get("assume_output")

    if not assumed:
        inputs, outputs = get_input_output(cls)

    if not inputs:
        warnings.warn("Cannot find correct types for %r" % cls)
        return

    s = " " * 4
    args_str = f",\n{s * 4}".join(f"{key}: {value}" for key, value in args.items())
    init_str = f",\n{s * 5}".join(f"{key}={key}" for key in args)
    input_str, output_str = repr(inputs), repr(outputs)
    base_class = base_classes[is_algorithm(cls)] #set correct base class

    print(cls)

    fp.write(textwrap.dedent(
        f"""
        from {cls.__module__} import {cls.__name__} as _{cls.__name__}

        @nice_repr
        class {cls.__name__}(_{cls.__name__}, {base_class}):
            def __init__(
                self,
                {args_str}
            ):
                {base_class}.__init__(self)
                _{cls.__name__}.__init__(
                    self,
                    {init_str}
                )

            def run(self, input: {input_str}) -> {output_str}:
               return {base_class}.run(self, input)
        """
    ))

    fp.flush()

def _walk(module, name="nltk"):
    imports = []

    def _walk_p(module, name="nltk"):
        all_elements = dir(module)
        for elem in all_elements:

            if elem == "exceptions":
                continue

            name = name + "." + elem

            try:
                obj = getattr(module, elem)

                if isinstance(obj, type):
                    # ignore nltk interfaces
                    if name.endswith("I"):
                        continue

                    if not _is_algorithm(obj):
                        continue

                    imports.append(obj)

                # _walk_p(obj, name) If not module do not walk in it
            except Exception as e:
                pass

            try:
                inner_module = importlib.import_module(name)
                _walk_p(inner_module, name)
            except:
                pass

    _walk_p(module, name)

    imports.sort(key=lambda c: (c.__module__, c.__name__))
    return imports


def _find_parameter_values(parameter, cls):
    documentation = []
    lines = cls.__doc__.split("\n")

    while lines:
        l = lines.pop(0)
        if l.strip().startswith(parameter):
            documentation.append(l)
            tabs = l.index(parameter)
            break

    while lines:
        l = lines.pop(0)

        if not l.strip():
            continue

        if l.startswith(" " * (tabs + 1)):
            documentation.append(l)
        else:
            break

    options = set(re.findall(r"'(\w+)'", " ".join(documentation)))
    valid = []
    invalid = []
    skip = set(["deprecated", "auto_deprecated", "precomputed"])

    for opt in options:
        opt = opt.lower()
        if opt in skip:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cls(**{parameter: opt}).fit(np.ones((10, 10)), [True] * 5 + [False] * 5)
                valid.append(opt)
        except Exception as e:
            invalid.append(opt)

    return sorted(valid)


def _find_language_values(cls):
    global languages_re
    documentation = cls.__doc__

    return set(languages_re.findall(str.lower(documentation)))


def _get_args(cls):
    full_specs = inspect.getfullargspec(cls.__init__)

    args = full_specs.args
    specs = full_specs.defaults

    if not args or not specs:
        return {}

    non_kwargs = [arg for arg in args[: -len(specs) :] if arg != "self"]

    args = args[-len(specs) :]

    args_map = {k: v for k, v in zip(args, specs)}



    drop_args = [
        "url",
        "n_jobs",
        "max_iter",
        "class_weight",
        "warm_start",
        "copy_X",
        "copy_x",
        "copy",
        "eps",
        "ignore_stopwords",
    ]

    for arg in drop_args:
        args_map.pop(arg, None)

    result = {}

    for arg, value in args_map.items():
        values = _get_arg_values(arg, value, cls)
        if not values:
            continue
        result[arg] = values

    for arg in non_kwargs:
        # special handling of language
        if str.lower(arg) == "language":
            values = _find_language_values(cls)
            if values:
                result[arg] = Categorical(*values)
                continue
        raise Exception("No values found for positional argument %s " % (arg))
    return result


def _get_arg_values(arg, value, cls):
    if isinstance(value, bool):
        return Boolean()
    if isinstance(value, int):
        return Discrete(*_get_integer_values(arg, value, cls))
    if isinstance(value, float):
        return Continuous(*_get_float_values(arg, value, cls))
    if isinstance(value, str):
        values = _find_parameter_values(arg, cls)
        return Categorical(*values) if values else None
    return None


def _get_integer_values(arg, value, cls):
    if value == 0:
        min_val = -100
        max_val = 100
    else:
        min_val = value // 2
        max_val = 2 * value

    return min_val, max_val


def _get_float_values(arg, value, cls):
    if value == 0:
        min_val = -1
        max_val = 1
    elif 0 < value <= 0.1:
        min_val = value / 100
        max_val = 1
    elif 0 < value <= 1:
        min_val = 1e-6
        max_val = 1
    else:
        min_val = value / 2
        max_val = 2 * value

    return min_val, max_val


if __name__ == "__main__":
    build_nltk_wrappers()
