from typing import Callable, Optional, Union, Any, List, Iterator
from collections import namedtuple

from convokit import Transformer, Corpus
from .utteranceSimulatorModel import UtteranceSimulatorModel
from .util import ContextTuple


class UtteranceSimulator(Transformer):
    """
    A wrapper class that provides a consistent interace to any UtteranceSimulatorModel
    instance. From a user perspective, this makes it easy to apply these models to ConvoKit
    corpora and swap between different models while maintaining the same interface.
    From a developer perspective, this provides a prebuilt foundation upon which
    new models can be easily developed.

    :param simulator_model: An instance of a UtteranceSimulatorModel subclass that
        implements the uttterance simulator model you want to use
    :param simulated_reply_attribute_name: Name of metadata field to save
        simulated replies generated by the simulator_model
    """

    def __init__(
        self,
        simulator_model: UtteranceSimulatorModel,
        simulated_reply_attribute_name: str = "sim_replies",
    ):
        self.simulator_model = simulator_model
        self.simulated_reply_attribute_name = simulated_reply_attribute_name

    @property
    def name(self):
        """
        Name of the simulator model.
        """
        return self._name

    @name.setter
    def name(self, name):
        """
        Sets the name of the simulator model.

        :param name: Name of model
        """
        self._name = name

    def fit(
        self,
        corpus=Corpus,
        context_selector: Callable[[ContextTuple], bool] = lambda context: True,
        val_context_selector: Callable[[ContextTuple], bool] = lambda context: True,
    ):
        """
        Wrapper method for fine-tuning the underlying utterance simulator model.
        Handles the creation of context iterators which are passed to the
        underlying `simulator_model` to process accordingly.

        :param corpus: Corpus containing the data to train on
        :param contexts: Function to select context tuples for training
        :param val_contexts: Function to select context tuples for validation

        :return: fitted UtteranceSimulator Transformer
        """
        contexts = self._create_context_iterator(
            corpus=corpus,
            context_selector=context_selector,
            include_future_context=True,
        )
        val_contexts = None
        if val_context_selector is not None:
            val_contexts = self._create_context_iterator(
                corpus=corpus,
                context_selector=val_context_selector,
                include_future_context=True,
            )
        self.simulator_model.fit(contexts, val_contexts)
        return self

    def transform(
        self,
        corpus: Corpus,
        context_selector: Callable[[ContextTuple], bool] = lambda context: True,
    ):
        """
        Wrapper method for applying the underlying utterance simulator model
        to generate replies over the conversation contexts. Handles the creation
        of context iterators which are passed to the underlying `simulator_model`
        to process accordingly.

        :param corpus: Corpus containing the data to run on
        :param contexts: Function to select context tuples to transform

        :return: annotated Corpus
        """
        contexts = self._create_context_iterator(corpus=corpus, context_selector=context_selector)
        simulations_df = self.simulator_model.transform(
            contexts,
            simulated_reply_attribute_name=self.simulated_reply_attribute_name,
        )

        for utt in corpus.iter_utterances():
            if utt.id in simulations_df.index:
                utt.add_meta(
                    self.simulated_reply_attribute_name,
                    simulations_df.loc[utt.id][self.simulated_reply_attribute_name],
                )
            else:
                utt.add_meta(self.simulated_reply_attribute_name, None)

        return corpus

    def _create_context_iterator(
        self,
        corpus: Corpus,
        context_selector: Callable[[ContextTuple], bool],
        include_future_context: bool = False,
    ):
        """
        Helper function that generates an iterator over conversational contexts
        that satisfy the provided context selector, across the entire corpus
        """
        for convo in corpus.iter_conversations():
            chronological_utts = convo.get_chronological_utterance_list()
            for i in range(len(chronological_utts)):
                current_utt = chronological_utts[i]
                context = chronological_utts[: (i + 1)]
                if include_future_context:
                    if i == len(chronological_utts) - 1:
                        future_context = []
                    else:
                        future_context = chronological_utts[(i + 1) :]
                else:
                    future_context = None
                context_tuple = ContextTuple(context, current_utt, future_context, convo.id)
                if len(context_tuple.context) == 0 or not context_selector(context_tuple):
                    continue
                yield context_tuple
