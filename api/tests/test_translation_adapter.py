import json

from api.constans import TaskStageConstants
from api.models import *
from api.tests import GigaTurnipTestHelper


class TranslationAdapterTest(GigaTurnipTestHelper):

    def test_translation_adapter_on_task_creation(self):
        schema = {
            "type": "object",
            "title": "Please pass your answers on below questions",
            "properties": {
                "answer": {
                    "title": "Pass something here.",
                    "type": "string"
                }
            },
            "required": ["answer"]
        }
        schema2 = {
            "type": "object",
            "title": "Please pass your answers on below questions",
            "properties": {
                "answer": {
                    "title": "Pass something here 2.",
                    "type": "string"
                }
            },
            "required": ["answer"]
        }
        schema3 = {
            "type": "object",
            "title": "Please pass your answers on below questions 2",
            "properties": {
                "answer": {
                    "title": "Pass something here.",
                    "type": "string"
                }
            },
            "required": ["answer"]
        }
        schema4 = {
            "type": "object",
            "title": "Please pass your answers on below questions",
            "properties": {
                "answer": {
                    "title": "Pass something here.",
                    "type": "string"
                }
            },
            "required": ["answer"]
        }
        self.initial_stage.json_schema = json.dumps(schema)
        self.initial_stage.save()

        # init second chain and stage
        chain2 = Chain.objects.create(
            name="Second chain",
            campaign=self.campaign
        )
        chain2_stage = TaskStage.objects.create(
            name="Pass last name",
            chain=chain2,
            json_schema=json.dumps(schema2),
            x_pos=1,
            y_pos=1,
            is_creatable=True,
        )
        self.prepare_client(
            chain2_stage,
            self.user,
            RankLimit(is_creation_open=True))

        # init third chain and stage
        chain3 = Chain.objects.create(
            name="Third chain",
            campaign=self.campaign
        )
        chain3_stage = TaskStage.objects.create(
            name="Pass surname",
            chain=chain3,
            json_schema=json.dumps(schema3),
            x_pos=1,
            y_pos=1,
            is_creatable=True,
        )
        self.prepare_client(
            chain3_stage,
            self.user,
            RankLimit(is_creation_open=True))

        # init third chain and stage
        chain4 = Chain.objects.create(
            name="Fourth chain",
            campaign=self.campaign
        )
        chain4_stage = TaskStage.objects.create(
            name="Pass surname",
            chain=chain4,
            json_schema=json.dumps(schema4),
            x_pos=1,
            y_pos=1,
            is_creatable=True,
        )
        self.prepare_client(
            chain4_stage,
            self.user,
            RankLimit(is_creation_open=True))

        # creating languages
        ru_lang = Language.objects.create(
            name="Russia",
            code="ru"
        )
        ky_lang = Language.objects.create(
            name="Kyrgyzstan",
            code="ky"
        )
        fr_lang = Language.objects.create(
            name="French",
            code="fr"
        )

        # create modifier
        ## first chain
        chain1_modifier_stage = self.initial_stage.add_stage(
            TaskStage(
                name="Translate adapter",
                assign_user_by=TaskStageConstants.RANK
            )
        )
        TranslationAdapter.objects.create(
            stage=chain1_modifier_stage,
            source=self.lang,
            target=ru_lang,
        )
        TranslationAdapter.objects.create(
            stage=chain1_modifier_stage,
            source=self.lang,
            target=ky_lang,
        )
        TranslationAdapter.objects.create(
            stage=chain1_modifier_stage,
            source=self.lang,
            target=fr_lang,
        )

        task_trigger = self.create_task(self.initial_stage)
        task_trigger = self.complete_task(task_trigger,
                                          {"answer": "Hello world!"})
        self.check_task_completion(task_trigger, self.initial_stage)
        self.assertTrue(
            all(self.initial_stage.tasks.values_list("complete", flat=True)))

        texts = ["Please pass your answers on below questions",
        "Pass something here.",
        "Pass something here 2.",
        "Please pass your answers on below questions 2"]
        keys = TranslateKey.objects.filter(campaign=self.campaign)
        self.assertEqual(keys.count(), 4)

        self.assertEqual(
            list(keys.values_list("text", flat=True).order_by("text")),
            sorted(texts)
        )
        self.assertEqual(TranslateKey.objects.all().count(), 4)
        self.assertEqual(Translation.objects.all().count(), 12)
        tasks_to_translate = chain1_modifier_stage.tasks.all()
        self.assertEqual(tasks_to_translate.count(), 9)

        expecting_schemas = [
            {'type': 'object',
             'title': 'Translate this phrases on Russia',
             'properties': {
                 '253c094b50c180b19aa2abaed698d54e759d4aabadc50189d4925aef4fff7e49': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions'},
                 '3bc69761604de2f66f3a0f7c6866abf832e86409581f567169b8875c87b69eac': {
                     'type': 'string',
                     'title': 'Pass something here.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on Russia',
             'properties': {
                 'fe02973b5a58a89f8ba943d54611a181a5941160abb5380b31e897727e2ee87f': {
                     'type': 'string',
                     'title': 'Pass something here 2.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on Russia',
             'properties': {
                 '19bf0b4cc72b2da0b08ccff59137ec0b0e292e4df777860ceea4de755042409c': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions 2'}}},
            {'type': 'object',
             'title': 'Translate this phrases on Kyrgyzstan',
             'properties': {
                 '253c094b50c180b19aa2abaed698d54e759d4aabadc50189d4925aef4fff7e49': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions'},
                 '3bc69761604de2f66f3a0f7c6866abf832e86409581f567169b8875c87b69eac': {
                     'type': 'string',
                     'title': 'Pass something here.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on Kyrgyzstan',
             'properties': {
                 'fe02973b5a58a89f8ba943d54611a181a5941160abb5380b31e897727e2ee87f': {
                     'type': 'string',
                     'title': 'Pass something here 2.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on Kyrgyzstan',
             'properties': {
                 '19bf0b4cc72b2da0b08ccff59137ec0b0e292e4df777860ceea4de755042409c': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions 2'}}},
            {'type': 'object',
             'title': 'Translate this phrases on French',
             'properties': {
                 '253c094b50c180b19aa2abaed698d54e759d4aabadc50189d4925aef4fff7e49': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions'},
                 '3bc69761604de2f66f3a0f7c6866abf832e86409581f567169b8875c87b69eac': {
                     'type': 'string',
                     'title': 'Pass something here.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on French',
             'properties': {
                 'fe02973b5a58a89f8ba943d54611a181a5941160abb5380b31e897727e2ee87f': {
                     'type': 'string',
                     'title': 'Pass something here 2.'}}},
            {'type': 'object',
             'title': 'Translate this phrases on French',
             'properties': {
                 '19bf0b4cc72b2da0b08ccff59137ec0b0e292e4df777860ceea4de755042409c': {
                     'type': 'string',
                     'title': 'Please pass your answers on below questions 2'}}}
        ]
        actual_schemas = [i for i in tasks_to_translate.values_list("schema", flat=True)]
        self.assertEqual(expecting_schemas, actual_schemas)

        # repeat actions if no schema didn't change
        task_trigger = self.create_task(self.initial_stage)
        task_trigger = self.complete_task(task_trigger,
                                          {"answer": "Hello world!"})
        self.assertTrue(task_trigger.complete)

        keys = TranslateKey.objects.filter(campaign=self.campaign)
        self.assertEqual(keys.count(), 4)

        self.assertEqual(
            list(keys.values_list("text", flat=True).order_by("text")),
            sorted(texts)
        )
        self.assertEqual(TranslateKey.objects.all().count(), 4)
        self.assertEqual(Translation.objects.all().count(), 12)
        tasks_to_translate = chain1_modifier_stage.tasks.all()
        self.assertEqual(tasks_to_translate.count(), 9)
