import json
from uuid import uuid4

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient

from api.constans import (
    TaskStageConstants, CopyFieldConstants, AutoNotificationConstants,
    ErrorConstants, WebhookConstants, TaskStageSchemaSourceConstants)
from api.models import CampaignLinker, ApproveLink, Language, Category, Country
from api.models import CustomUser, TaskStage, Campaign, Chain, \
    ConditionalStage, Stage, Rank, RankRecord, RankLimit, \
    Task, CopyField, Integration, Quiz, ResponseFlattener, Log, \
    AdminPreference, Track, TaskAward, Notification, \
    DynamicJson, PreviousManual, Webhook, AutoNotification, NotificationStatus, \
    ConditionalLimit, DatetimeSort, \
    ErrorGroup, ErrorItem, CampaignManagement


def to_json(string):
    return json.loads(string)


class GigaTurnipTest(APITestCase):

    def create_client(self, u):
        client = APIClient()
        client.force_authenticate(u)
        return client

    def prepare_client(self, stage, user=None, rank_limit=None):
        u = user
        if u is None:
            user_name = str(uuid4())
            u = CustomUser.objects.create_user(
                username=user_name,
                email=user_name + "@email.com",
                password='test')
        rank = Rank.objects.create(name=stage.name)
        RankRecord.objects.create(
            user=u,
            rank=rank)
        rank_l = rank_limit
        if rank_l is None:
            rank_l = RankLimit.objects.create(
                rank=rank,
                stage=stage,
                open_limit=0,
                total_limit=0,
                is_listing_allowed=True,
                is_creation_open=False)
        else:
            rank_l.rank = rank
            rank_l.stage = stage
        rank_l.save()
        return self.create_client(u)

    def generate_new_basic_campaign(self, name, lang=None, countries=None):
        l = lang
        if not l:
            l = self.lang
        c = countries
        if not c:
            c = [self.country]

        campaign = Campaign.objects.create(name=name, language=l)
        campaign.countries.set(c)
        default_track = Track.objects.create(
            campaign=campaign,

        )
        campaign.default_track = default_track
        rank = Rank.objects.create(name=f"Default {name} rank",
                                   track=default_track)
        default_track.default_rank = rank
        campaign.save()
        default_track.save()

        chain = Chain.objects.create(
            name=f"Default {name} chain",
            campaign=campaign
        )
        return {
            "campaign": campaign,
            "default_track": default_track,
            "rank": rank,
            "chain": chain
        }

    def setUp(self):
        self.lang = Language.objects.create(
            name="English",
            code="en"
        )
        self.category = Category.objects.create(
            name="Commerce"
        )
        self.country = Country.objects.create(
            name="Vinland"
        )


        basic_data = self.generate_new_basic_campaign("Coca-Cola")

        self.campaign = basic_data['campaign']
        self.campaign.categories.add(self.category)
        self.default_track = basic_data['default_track']
        self.default_rank = basic_data['rank']
        self.chain = basic_data['chain']
        self.initial_stage = TaskStage.objects.create(
            name="Initial",
            x_pos=1,
            y_pos=1,
            chain=self.chain,
            is_creatable=True)
        self.user = CustomUser.objects.create_user(username="test",
                                                   email='test@email.com',
                                                   password='test')

        self.employee = CustomUser.objects.create_user(username="employee",
                                                       email='employee@email.com',
                                                       password='employee')
        self.employee_client = self.create_client(self.employee)

        self.client = self.prepare_client(
            self.initial_stage,
            self.user,
            RankLimit(is_creation_open=True))

    def get_objects(self, endpoint, params=None, client=None, pk=None):
        c = client
        if c is None:
            c = self.client
        if pk:
            url = reverse(endpoint, kwargs={"pk": pk})
        else:
            url = reverse(endpoint)
        if params:
            return c.get(url, data=params)
        else:
            return c.get(url)

    def create_task(self, stage, client=None):
        c = client
        task_create_url = reverse(
            "taskstage-create-task",
            kwargs={"pk": stage.pk})
        if c is None:
            c = self.client
        response = c.get(task_create_url)
        return Task.objects.get(id=response.data["id"])

    def request_assignment(self, task, client=None):
        c = client
        request_assignment_url = reverse(
            "task-request-assignment",
            kwargs={"pk": task.pk})
        if c is None:
            c = self.client
        response = c.get(request_assignment_url)
        task = Task.objects.get(id=response.data["id"])
        self.assertEqual(response.wsgi_request.user, task.assignee)
        return task

    def create_initial_task(self):
        return self.create_task(self.initial_stage)

    def create_initial_tasks(self, count):
        return [self.create_initial_task() for x in range(count)]

    def complete_task(self, task, responses=None, client=None, whole_response=False):
        c = client
        if c is None:
            c = self.client
        task_update_url = reverse("task-detail", kwargs={"pk": task.pk})
        if responses:
            args = {"complete": True, "responses": responses}
        else:
            args = {"complete": True}
        response = c.patch(task_update_url, args, format='json')
        if not whole_response and response.data.get('id'):
            return Task.objects.get(id=response.data["id"])
        elif whole_response:
            return response
        else:
            return response

    def update_task_responses(self, task, responses, client=None):
        c = client
        if c is None:
            c = self.client
        task_update_url = reverse("task-detail", kwargs={"pk": task.pk})
        args = {"responses": responses}
        response = c.patch(task_update_url, args, format='json')
        return Task.objects.get(id=response.data["id"])

    def check_task_manual_creation(self, task, stage):
        self.assertEqual(task.stage, stage)
        self.assertFalse(task.complete)
        self.assertFalse(task.force_complete)
        self.assertFalse(task.reopened)
        self.assertIsNone(task.integrator_group)
        self.assertFalse(task.in_tasks.exists())
        self.assertIsNone(task.responses)
        self.assertEqual(len(Task.objects.filter(stage=task.stage)), 1)

    def check_task_auto_creation(self, task, stage, initial_task):
        self.assertEqual(task.stage, stage)
        self.assertFalse(task.complete)
        self.assertFalse(task.force_complete)
        self.assertFalse(task.reopened)
        self.assertIsNone(task.integrator_group)
        self.assertTrue(task.in_tasks.exists())
        self.assertIn(initial_task.id, task.in_tasks.values_list("id", flat=True))
        self.assertTrue(len(task.in_tasks.values_list("id", flat=True)) == 1)
        self.assertEqual(len(Task.objects.filter(stage=task.stage)), 1)

    def check_task_completion(self, task, stage, responses=None):
        self.assertEqual(task.stage, stage)
        self.assertTrue(task.complete)
        self.assertFalse(task.force_complete)
        self.assertFalse(task.reopened)
        self.assertIsNone(task.integrator_group)
        self.assertFalse(task.in_tasks.exists())
        if responses is not None:
            self.assertEqual(task.responses, responses)
        self.assertEqual(len(Task.objects.filter(stage=task.stage)), 1)

    def test_list_languages(self):
        Language.objects.create(
            code="ru",
            name="Russian"
        )
        Language.objects.create(
            code="ky",
            name="Kyrgyz"
        )

        response = self.get_objects("language-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 3)
        langs_en_data = {
            "id": self.lang.id,
            "name": self.lang.name,
            "code": self.lang.code
        }
        self.assertIn(langs_en_data, content["results"])

    def test_list_countries(self):
        Country.objects.create(
            name="Russian"
        )
        Country.objects.create(
            name="Kyrgyzstan"
        )

        response = self.get_objects("country-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 3)
        country_data = {
            "id": self.country.id,
            "name": self.country.name
        }
        self.assertIn(country_data, content["results"])

    def test_list_campaign_serializer(self):
        # join employee to campaign
        self.campaign.open = True
        self.campaign.save()
        response = self.employee_client.get(
            reverse("campaign-join-campaign", kwargs={"pk": self.campaign.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        Notification.objects.create(
            title="title",
            campaign=self.campaign,
            target_user=self.employee
        )
        Notification.objects.create(
            title="title",
            campaign=self.campaign,
            rank=self.default_rank
        )
        Notification.objects.create(
            title="title",
            campaign=self.campaign,
        )
        response = self.get_objects("campaign-list", client=self.employee_client)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            to_json(response.content)["results"][0]["notifications_count"], 2)

        response = self.client.get(
            reverse("campaign-join-campaign", kwargs={"pk": self.campaign.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.get_objects("campaign-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            to_json(response.content)["results"][0]["notifications_count"], 1)


        new_user = CustomUser.objects.create_user(username="new_new",
                                                       email='new_new@email.com',
                                                       password='123')
        new_user_client = self.create_client(new_user)
        response = self.get_objects("campaign-list", client=new_user_client)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            to_json(response.content)["results"][0]["notifications_count"], 0)

    def test_campaign_filters_by_language(self):
        campaign_en_data = self.generate_new_basic_campaign(name="Pepsi")
        campaign_ru_data = self.generate_new_basic_campaign(name="Добрый Кола")
        campaign_ky_data = self.generate_new_basic_campaign(name="Джакшы Кола")

        lang_ru = Language.objects.create(
            name="Russian",
            code="ru"
        )
        lang_ky = Language.objects.create(
            name="Kyrgyz",
            code="ky"
        )

        campaign_ru_data["campaign"].language = lang_ru
        campaign_ky_data["campaign"].language = lang_ky

        campaign_ru_data["campaign"].open = True
        campaign_ky_data["campaign"].open = True

        campaign_ru_data["campaign"].save()
        campaign_ky_data["campaign"].save()

        response = self.get_objects("campaign-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(to_json(response.content)['count'], 4)

        response = self.get_objects("campaign-list",
                                    params={"language__code": "ru"}
                                    )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(to_json(response.content)['count'], 1)
        self.assertEqual(to_json(response.content)['results'][0]['id'],
                         campaign_ru_data['campaign'].id)

        response = self.get_objects("campaign-list",
                                    params={"language__code": "ky"}
                                    )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(to_json(response.content)['count'], 1)
        self.assertEqual(to_json(response.content)['results'][0]['id'],
                         campaign_ky_data['campaign'].id)

        response = self.get_objects("campaign-list",
                                    params={"language__code": "en"}
                                    )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(to_json(response.content)['count'], 2)
        for i in [campaign_en_data['campaign'].id, self.campaign.id]:
            self.assertIn(i, [_['id'] for _ in
                              to_json(response.content)['results']])

    def test_list_categories(self):
        products_category = Category.objects.create(
            name="Producs"
        )

        e_commerce_category = Category.objects.create(
            name="E-Commerce"
        )
        e_commerce_category.parents.add(self.category)

        electronics_category = Category.objects.create(
            name="Electronics"
        )
        pcs_category = Category.objects.create(
            name="Personal computers"
        )
        pcs_devices_category = Category.objects.create(
            name="Personal computers attributes."
        )
        pcs_mouses_category = Category.objects.create(
            name="Mouses"
        )

        electronics_category.out_categories.add(pcs_category)
        electronics_category.out_categories.add(pcs_devices_category)
        pcs_devices_category.out_categories.add(pcs_mouses_category)

        answer = [
            {
                'id': self.category.id,
                'name': self.category.name,
                'out_categories': [
                    e_commerce_category.id
                ]},
            {
                'id': e_commerce_category.id,
                'name': e_commerce_category.name,
                'out_categories': []},
            {
                'id': electronics_category.id,
                'name': electronics_category.name,
                'out_categories': [
                    pcs_category.id,
                    pcs_devices_category.id
                ]
            },
            {
                'id': pcs_mouses_category.id,
                'name': pcs_mouses_category.name,
                'out_categories': []},
            {
                'id': pcs_category.id,
                'name': pcs_category.name,
                'out_categories': []
            },
            {
                'id': pcs_devices_category.id,
                'name': pcs_devices_category.name,
                'out_categories': [pcs_mouses_category.id]
            },
            {
                'id': products_category.id,
                'name': products_category.name,
                'out_categories': []
            }
        ]
        response = self.get_objects("category-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], Category.objects.count())
        self.assertEqual(content["results"], answer)

    def test_filter_campaign_by_categories_in(self):
        products_category = Category.objects.create(
            name="Producs"
        )

        e_commerce_category = Category.objects.create(
            name="E-Commerce"
        )
        e_commerce_category.parents.add(self.category)

        electronics_category = Category.objects.create(
            name="Electronics"
        )
        pcs_category = Category.objects.create(
            name="Personal computers"
        )
        pcs_devices_category = Category.objects.create(
            name="Personal computers attributes."
        )
        pcs_mouses_category = Category.objects.create(
            name="Mouses"
        )

        electronics_category.out_categories.add(pcs_category)
        electronics_category.out_categories.add(pcs_devices_category)
        pcs_devices_category.out_categories.add(pcs_mouses_category)

        answer = [
            {
                'id': self.category.id,
                'name': self.category.name,
                'out_categories': [
                    e_commerce_category.id
                ]},
            {
                'id': e_commerce_category.id,
                'name': e_commerce_category.name,
                'out_categories': []},
            {
                'id': electronics_category.id,
                'name': electronics_category.name,
                'out_categories': [
                    pcs_category.id,
                    pcs_devices_category.id
                ]
            },
            {
                'id': pcs_mouses_category.id,
                'name': pcs_mouses_category.name,
                'out_categories': []},
            {
                'id': pcs_category.id,
                'name': pcs_category.name,
                'out_categories': []
            },
            {
                'id': pcs_devices_category.id,
                'name': pcs_devices_category.name,
                'out_categories': [pcs_mouses_category.id]
            },
            {
                'id': products_category.id,
                'name': products_category.name,
                'out_categories': []
            }
        ]
        response = self.get_objects("category-list")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], Category.objects.count())
        self.assertEqual(content["results"], answer)

        campaign_e_commerce = self.generate_new_basic_campaign(name="ElPay")
        campaign_products = self.generate_new_basic_campaign(name="Pepsi")
        campaign_electronics = self.generate_new_basic_campaign(name="Techno")
        campaign_pcs = self.generate_new_basic_campaign(name="Personal droid")
        campaign_pcs_attributes = self.generate_new_basic_campaign(name="Techno mouse")

        campaign_e_commerce["campaign"].categories.add(e_commerce_category)
        campaign_products["campaign"].categories.add(products_category)
        campaign_electronics["campaign"].categories.add(electronics_category)
        campaign_pcs["campaign"].categories.add(pcs_category)
        campaign_pcs["campaign"].categories.add(pcs_devices_category)
        campaign_pcs_attributes["campaign"].categories.add(pcs_devices_category)

        response = self.get_objects("campaign-list",
                                    params={})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 6)

        response = self.get_objects("campaign-list",
                                    params={
                                        "categories": electronics_category.id
                                    })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 1)

        response = self.get_objects("campaign-list",
                                    params={
                                        "category_in": electronics_category.id
                                    })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 2)
        ids = [i["id"] for i in content["results"]]
        self.assertIn(campaign_pcs["campaign"].id, ids)
        self.assertIn(campaign_pcs_attributes["campaign"].id, ids)

    def test_filter_campaigns_by_country_name(self):
        rus_country = Country.objects.create(
            name="Russian"
        )
        kyz_country = Country.objects.create(
            name="Kyrgyzstan"
        )

        pepsi = self.generate_new_basic_campaign("Pepsi", countries=[rus_country, kyz_country])
        fanta = self.generate_new_basic_campaign("Fanta", countries=[rus_country])

        response = self.get_objects("campaign-list", params={
            "countries__name": self.country.name}
                                    )
        # print([i.countries.all() for i in Campaign.objects.all()])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        # print(content)
        self.assertEqual(content["count"], 1)
        self.assertEqual(self.campaign.id, content["results"][0]["id"])


        response = self.get_objects("campaign-list", params={
            "countries__name": rus_country.name}
                                    )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = to_json(response.content)
        self.assertEqual(content["count"], 2)
        for i in [pepsi["campaign"].id, fanta["campaign"].id]:
            self.assertIn(i, [_["id"] for _ in content["results"]])

    def test_initial_task_creation(self):
        task = self.create_initial_task()
        self.check_task_manual_creation(task, self.initial_stage)

    def test_TaskStageViewSet_public_paginate(self):
        response = self.get_objects('taskstage-public')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(json.loads(response.content).keys()),
            {"count", "next", "previous", "results"}
            )

    def test_TaskStageViewSet_user_relevant_paginate(self):
        response = self.get_objects('taskstage-user-relevant')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(json.loads(response.content).keys()),
            {"count", "next", "previous", "results"}
        )

    def test_task_stage_serializers_by_flag(self):
        self.user.managed_campaigns.add(self.campaign)
        response = self.get_objects('taskstage-list')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.initial_stage.id)
        ranks = response.data['results'][0]['ranks']
        self.assertEqual(len(ranks), self.initial_stage.ranks.count())
        self.assertEqual(ranks, list(self.initial_stage.ranks.values_list('id', flat=True)))

        image = '<i class="fa-solid fa-filter"></i>'
        rank = self.initial_stage.ranks.filter(id=self.initial_stage.ranks.all()[0].id).update(avatar=image)
        response = self.get_objects('taskstage-list', params={"ranks_avatars": "yes"})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.initial_stage.id)
        ranks = response.data['results'][0]['ranks']
        stage_rank = self.initial_stage.ranks.all()[0]
        self.assertEqual(len(ranks), self.initial_stage.ranks.count())
        self.assertEqual(ranks[0]['avatar'], stage_rank.avatar)

    def test_initial_task_completion(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        self.initial_stage.save()
        task = self.create_initial_task()
        responses = {"answer": "check"}
        task = self.complete_task(task, responses=responses)

        self.check_task_completion(task, self.initial_stage, responses)

    def test_initial_task_update_and_completion(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        self.initial_stage.save()
        task = self.create_initial_task()
        responses = {"answer": "check"}
        updated_task = self.update_task_responses(task, responses)
        self.assertEqual(updated_task.responses, responses)
        new_responses = {"answer": "check check"}
        completed_task = self.complete_task(task, new_responses)
        self.check_task_completion(
            completed_task,
            self.initial_stage,
            new_responses)

    def test_initial_task_update_and_completion_no_responses(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        self.initial_stage.save()
        task = self.create_initial_task()
        responses = {"answer": "check"}
        updated_task = self.update_task_responses(task, responses)
        self.assertEqual(updated_task.responses, responses)
        completed_task = self.complete_task(task)
        self.check_task_completion(
            completed_task,
            self.initial_stage,
            responses)

    def test_add_stage(self):
        self.initial_stage.add_stage(ConditionalStage()).add_stage(TaskStage())
        stages_queryset = Stage.objects.filter(chain=self.chain)
        self.assertEqual(len(stages_queryset), 3)

    def test_simple_chain(self):
        second_stage = self.initial_stage.add_stage(TaskStage())
        initial_task = self.create_initial_task()
        self.complete_task(initial_task)
        second_task = initial_task.out_tasks.get()
        self.check_task_auto_creation(second_task, second_stage, initial_task)

    def test_conditional_stage_api_creation(self):
        self.user.managed_campaigns.add(self.campaign)
        url = 'conditionalstage-list'

        conditional = {
            'name': 'Checker', 'chain': self.chain.id, 'x_pos': 1, 'y_pos': 1,
            'conditions': []
        }

        response = self.client.post(reverse(url), data=conditional)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        conditional = {
            'name': 'Checker', 'chain': self.chain.id, 'x_pos': 1, 'y_pos': 1,
            'conditions': json.dumps([{"ssf": "world"}])
        }

        response = self.client.post(reverse(url), data=conditional)
        self.assertEqual(response.data['message'], 'Invalid data in 1 index. Please, provide \'type\' field')

        conditional = {
            'name': 'Checker', 'chain': self.chain.id, 'x_pos': 1, 'y_pos': 1,
            'conditions': json.dumps([{"type": "herere"}])
        }

        response = self.client.post(reverse(url), data=conditional)
        self.assertEqual(response.data['message'], 'Invalid data in 1 index. Please, provide valid type')

        conditional = {
            'name': 'Checker', 'chain': self.chain.id, 'x_pos': 1, 'y_pos': 1,
            'conditions': json.dumps([
                {"type": "string", 'value': "something", 'field': 'verification', 'condition':'=='}
            ])
        }

        response = self.client.post(reverse(url), data=conditional)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_conditional_stage(self):
        self.user.managed_campaigns.add(self.campaign)
        conditions = [{
            "field": "verified",
            "value": "Нет",
            "condition": "=="
        }]
        conditional_stage = {
            "name": "My Conditional Stage",
            "chain": self.initial_stage.chain.id,
            "x_pos": 1,
            "y_pos": 1,
            "conditions": json.dumps(conditions),
            "pingpong": False,
        }
        response = self.client.post(reverse('conditionalstage-list'), data=conditional_stage)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], "Invalid data in 1 index. Please, provide 'type' field")

        conditions[0]['type'] = 'number'
        conditional_stage['conditions'] = json.dumps(conditions)
        response = self.client.post(reverse('conditionalstage-list'), data=conditional_stage)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'],
                         "Invalid data in 1 index. 'Нет' is not of type 'number'")

        conditions[0]['value'] = 15
        conditional_stage['conditions'] = json.dumps(conditions)
        response = self.client.post(reverse('conditionalstage-list'), data=conditional_stage)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_conditional_limit_main_logic(self):
        first_schema = {"type": "object", "title": "Поздоровайтесь ", "properties": {"newInput1": {"title": "Hi!", "type": "integer"}},
         "dependencies": {}, "required": []}
        self.initial_stage.json_schema = json.dumps(first_schema)
        self.initial_stage.save()

        # create conditional stages and limits
        conditional_water = self.initial_stage.add_stage(
            ConditionalStage(
                name='Вопрос воды',
                conditions=[{"type": "integer", "field": "newInput1", "value": 1, "condition": ">"}]
            )
        )
        cond_limit_1 = ConditionalLimit.objects.create(
            conditional_stage=conditional_water,
            order=3
        )

        conditional_gas = self.initial_stage.add_stage(
            ConditionalStage(
                name='Вопрос газа',
                conditions=[{"type": "integer", "field": "newInput1", "value": 1, "condition": ">"}]
            )
        )
        cond_limit_2 = ConditionalLimit.objects.create(
            conditional_stage=conditional_gas,
            order=1
        )

        conditional_cheburek = self.initial_stage.add_stage(
            ConditionalStage(
                name='Вопрос чебуреков',
                conditions=[{"type": "integer", "field": "newInput1", "value": 1, "condition": ">"}]
            )
        )
        cond_limit_3 = ConditionalLimit.objects.create(
            conditional_stage=conditional_cheburek,
            order=2
        )

        # create further stages with questions
        finish_water = conditional_water.add_stage(
            TaskStage(
                name='Цена воды',
                json_schema='{"type":"object","title":"цена воды такая-то"}',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage
            )
        )
        finish_gas = conditional_gas.add_stage(
            TaskStage(
                name='Цена газа',
                json_schema='{"type":"object","title":"цена газа такая-то"}',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage
            )
        )
        finish_cheburek = conditional_cheburek.add_stage(
            TaskStage(
                name='Цена чебуреков',
                json_schema='{"type":"object","title":"цена чебуреков такая-то"}',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage
            )
        )

        responses = {'newInput1': 0}
        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, responses)
        self.assertEqual(initial_task.out_tasks.count(), 1)
        self.assertEqual(initial_task.out_tasks.get().stage, finish_gas)
        next_task = self.complete_task(initial_task.out_tasks.get())

        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, responses)
        self.assertEqual(initial_task.out_tasks.count(), 1)
        self.assertEqual(initial_task.out_tasks.get().stage, finish_cheburek)
        next_task = self.complete_task(initial_task.out_tasks.get())

        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, responses)
        self.assertEqual(initial_task.out_tasks.count(), 1)
        self.assertEqual(initial_task.out_tasks.get().stage, finish_water)
        next_task = self.complete_task(initial_task.out_tasks.get())

        self.assertEqual(Task.objects.filter(assignee=self.user).count(), 6)

    def test_passing_conditional(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "verified": {
                    "enum": ["yes", "no"],
                    "type": "string"}
            },
            "required": ["verified"]
        })
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                conditions=[{"field": "verified", "type": "string", "value": "yes", "condition": "=="}]
            ))
        last_task_stage = conditional_stage.add_stage(TaskStage())
        initial_task = self.create_initial_task()
        responses = {"verified": "yes"}
        self.complete_task(initial_task, responses)
        new_task = initial_task.case.tasks.get(stage=last_task_stage)
        self.check_task_auto_creation(new_task, last_task_stage, initial_task)

    def test_failing_conditional(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "verified": {
                    "enum": ['yes', 'no'],
                    "type": "string"
                }
            },
            "required": ["verified"]
        })
        self.initial_stage.save()

        conditional_stage = ConditionalStage()
        conditional_stage.conditions = [
            {"field": "verified", "type": "string", "value": "yes", "condition": "=="}
        ]
        conditional_stage = self.initial_stage.add_stage(conditional_stage)
        last_task_stage = conditional_stage.add_stage(TaskStage())
        initial_task = self.create_initial_task()
        responses = {"verified": "no"}
        initial_task = self.update_task_responses(initial_task, responses)
        self.complete_task(initial_task, responses)
        new_task = initial_task.case.tasks.filter(stage=last_task_stage).exists()
        self.assertFalse(new_task)

    def test_pingpong(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        self.initial_stage.save()

        verification_task_stage = self.initial_stage \
            .add_stage(
                ConditionalStage(
                    conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                    pingpong=True
                )
            ).add_stage(TaskStage())

        final_task_stage = verification_task_stage.add_stage(TaskStage())
        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        responses = {"answer": "something"}
        initial_task = self.complete_task(initial_task, responses)

        verification_task = initial_task.out_tasks.get()

        self.request_assignment(verification_task, verification_client)

        verification_task = self.complete_task(
            verification_task,
            responses={"verified": "no"},
            client=verification_client)

        self.assertTrue(verification_task.complete)
        self.assertEqual(len(Task.objects.filter(case=initial_task.case)), 2)
        self.assertEqual(len(Task.objects.filter()), 2)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertEqual(initial_task.stage, self.initial_stage)
        self.assertFalse(initial_task.complete)
        self.assertFalse(initial_task.force_complete)
        self.assertTrue(initial_task.reopened)
        self.assertIsNone(initial_task.integrator_group)
        self.assertFalse(initial_task.in_tasks.exists())
        self.assertEqual(initial_task.responses, responses)
        self.assertEqual(len(Task.objects.filter(stage=initial_task.stage)), 1)

        initial_task = self.complete_task(initial_task)

        self.assertTrue(initial_task.complete)

        verification_task = Task.objects.get(id=verification_task.id)

        self.assertFalse(verification_task.complete)
        self.assertTrue(verification_task.reopened)
        self.assertEqual(len(Task.objects.filter()), 2)

        verification_task = self.complete_task(verification_task,
                                               responses={"verified": "yes"},
                                               client=verification_client)

        self.assertTrue(verification_task.complete)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)

        self.assertEqual(len(Task.objects.filter()), 3)
        self.assertEqual(len(Task.objects.filter(case=initial_task.case, stage=final_task_stage)), 1)

        final_task = Task.objects.get(case=initial_task.case, stage=final_task_stage)

        self.assertFalse(final_task.complete)
        self.assertIsNone(final_task.assignee)

    def test_pingpong_first_pass(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        self.initial_stage.save()

        verification_task_stage = self.initial_stage \
            .add_stage(
                ConditionalStage(
                    conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                    pingpong=True)
        ).add_stage(TaskStage())
        verification_task_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "verified": {
                    "enum": ['yes', 'no'],
                    "type": "string"
                }
            },
            "required": ["verified"]
        })
        verification_task_stage.save()

        final_task_stage = verification_task_stage.add_stage(TaskStage())

        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, {"answer": "something"})

        verification_task = initial_task.out_tasks.get()
        self.check_task_auto_creation(
            verification_task,
            verification_task_stage,
            initial_task)
        self.request_assignment(verification_task, verification_client)

        verification_task = self.complete_task(
            verification_task,
            {"verified": "yes"},
            verification_client)

        self.assertTrue(verification_task.complete)
        self.assertEqual(len(Task.objects.filter(case=initial_task.case)), 3)
        self.assertEqual(len(Task.objects.filter()), 3)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)
        self.assertEqual(len(Task.objects.filter()), 3)
        self.assertEqual(len(Task.objects.filter(case=initial_task.case, stage=final_task_stage)), 1)

        final_task = Task.objects.get(case=initial_task.case, stage=final_task_stage)

        self.check_task_auto_creation(
            final_task,
            final_task_stage,
            verification_task)
        self.assertFalse(final_task.assignee)

    def test_copy_field(self):
        id_chain = Chain.objects.create(name="Chain", campaign=self.campaign)
        id_stage = TaskStage.objects.create(
            name="ID",
            x_pos=1,
            y_pos=1,
            chain=id_chain,
            json_schema='{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}',
            is_creatable=True)
        self.client = self.prepare_client(
            id_stage,
            self.user,
            RankLimit(is_creation_open=True))
        task1 = self.create_task(id_stage)

        task1 = self.complete_task(
            task1,
            {"name": "rinat", "phone": 2, "address": "ssss"}
        )

        CopyField.objects.create(
            copy_by="US",
            task_stage=self.initial_stage,
            copy_from_stage=id_stage,
            fields_to_copy="name->name phone->phone1 absent->absent")

        task = self.create_initial_task()

        self.assertEqual(len(task.responses), 2)
        self.assertEqual(task.responses["name"], task1.responses["name"])
        self.assertEqual(task.responses["phone1"], task1.responses["phone"])

    def test_copy_field_with_no_source_task(self):
        id_chain = Chain.objects.create(name="Chain", campaign=self.campaign)
        id_stage = TaskStage.objects.create(
            name="ID",
            x_pos=1,
            y_pos=1,
            chain=id_chain,
            is_creatable=True)

        CopyField.objects.create(
            copy_by="US",
            task_stage=self.initial_stage,
            copy_from_stage=id_stage,
            fields_to_copy="name->name phone->phone1 absent->absent")

        task = self.create_initial_task()

        self.check_task_manual_creation(task, self.initial_stage)

    def test_copy_field_fail_for_different_campaigns(self):
        campaign = Campaign.objects.create(name="Campaign")
        id_chain = Chain.objects.create(name="Chain", campaign=campaign)
        id_stage = TaskStage.objects.create(
            name="ID",
            x_pos=1,
            y_pos=1,
            json_schema='{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}',
            chain=id_chain,
            is_creatable=True)
        self.client = self.prepare_client(
            id_stage,
            self.user,
            RankLimit(is_creation_open=True))
        task1 = self.create_task(id_stage)
        task2 = self.create_task(id_stage)
        task3 = self.create_task(id_stage)

        correct_responses = {"name": "kloop", "phone": 3, "address": "kkkk"}

        task1 = self.complete_task(
            task1,
            {"name": "rinat", "phone": 2, "address": "ssss"})
        task3 = self.complete_task(
            task3,
            {"name": "ri", "phone": 5, "address": "oooo"})
        task2 = self.complete_task(task2, correct_responses)

        CopyField.objects.create(
            copy_by="US",
            task_stage=self.initial_stage,
            copy_from_stage=id_stage,
            fields_to_copy="name->name phone->phone1 absent->absent")

        task = self.create_initial_task()

        self.assertIsNone(task.responses)

    def test_TaskViewSet_get_integrated_tasks_paginate(self):
        task = self.create_initial_task()
        response = self.get_objects("task-get-integrated-tasks", pk=task.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(json.loads(response.content).keys()),
            {"count", "next", "previous", "results"}
        )

    def test_get_tasks_selectable(self):
        second_stage = self.initial_stage.add_stage(TaskStage())
        self.client = self.prepare_client(second_stage, self.user)
        task_1 = self.create_initial_task()
        task_1 = self.complete_task(task_1)
        task_2 = task_1.out_tasks.all()[0]
        response = self.get_objects("task-user-selectable")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], task_2.id)

    def test_open_previous(self):
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage,
                allow_go_back=True
            ))
        initial_task = self.create_initial_task()
        self.complete_task(initial_task, responses={})

        second_task = Task.objects.get(
            stage=second_stage,
            case=initial_task.case)
        self.assertEqual(initial_task.assignee, second_task.assignee)

        response = self.get_objects("task-open-previous", pk=second_task.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], initial_task.id)

        initial_task = Task.objects.get(id=initial_task.id)
        second_task = Task.objects.get(id=second_task.id)

        self.assertTrue(second_task.complete)
        self.assertTrue(initial_task.reopened)
        self.assertFalse(initial_task.complete)
        self.assertEqual(Task.objects.all().count(), 2)

        initial_task = self.complete_task(initial_task)

        second_task = Task.objects.get(id=second_task.id)

        self.assertTrue(initial_task.complete)
        self.assertEqual(Task.objects.all().count(), 2)
        self.assertFalse(second_task.complete)
        self.assertTrue(second_task.reopened)

    def test_integration(self):
        self.initial_stage.json_schema = '{"type": "object","properties": {"oik": {"type": "integer"},"data": {"type": "string"}}}'
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(TaskStage())
        Integration.objects.create(
            task_stage=second_stage,
            group_by="oik")
        initial_task1 = self.create_initial_task()
        self.complete_task(initial_task1, responses={"oik": 4, "data": "elkfj"})
        initial_task2 = self.create_initial_task()
        self.complete_task(initial_task2, responses={"oik": 4, "data": "wlfij"})
        initial_task3 = self.create_initial_task()
        self.complete_task(initial_task3, responses={"oik": 4, "data": "sqj"})
        initial_task4 = self.create_initial_task()
        self.complete_task(initial_task4, responses={"oik": 5, "data": "saxha"})
        initial_task5 = self.create_initial_task()
        self.complete_task(initial_task5, responses={"oik": 5, "data": "sodhj"})

        self.assertEqual(Task.objects.filter(stage=second_stage).count(), 2)

        oik_4_integrator = Task.objects.get(integrator_group={"oik": 4})
        oik_5_integrator = Task.objects.get(integrator_group={"oik": 5})

        self.assertEqual(oik_4_integrator.in_tasks.all().count(), 3)
        self.assertEqual(oik_5_integrator.in_tasks.all().count(), 2)

        self.assertIn(initial_task1.id,
                      oik_4_integrator.in_tasks.all().values_list("id", flat=True))
        self.assertIn(initial_task2.id,
                      oik_4_integrator.in_tasks.all().values_list("id", flat=True))
        self.assertIn(initial_task3.id,
                      oik_4_integrator.in_tasks.all().values_list("id", flat=True))

        self.assertIn(initial_task4.id,
                      oik_5_integrator.in_tasks.all().values_list("id", flat=True))
        self.assertIn(initial_task5.id,
                      oik_5_integrator.in_tasks.all().values_list("id", flat=True))

    def test_closed_submission(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "dependencies": {},
            "required": ["answer"]
        })
        self.initial_stage.save()
        task = self.create_initial_task()
        responses = {"answer": "check"}
        updated_task = self.update_task_responses(task, responses)
        self.assertEqual(updated_task.responses, responses)
        client = self.prepare_client(
            task.stage,
            self.user,
            RankLimit(is_submission_open=False))
        task_update_url = reverse("task-detail", kwargs={"pk": task.pk})
        response = client.patch(task_update_url, {"complete": True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_copy_field_by_case(self):
        self.initial_stage.json_schema = '{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}'
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage)
        )
        third_stage = second_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                json_schema='{"type": "object","properties": {"name": {"type": "string"},"phone1": {"type": "integer"},"absent": {"type": "string"}}}',
                assign_user_from_stage=self.initial_stage)
        )
        CopyField.objects.create(
            copy_by=CopyFieldConstants.CASE,
            task_stage=third_stage,
            copy_from_stage=self.initial_stage,
            fields_to_copy="name->name phone->phone1 absent->absent")

        task = self.create_initial_task()
        correct_responses = {"name": "kloop", "phone": 3, "address": "kkkk"}
        task = self.complete_task(task, responses=correct_responses)
        task_2 = task.out_tasks.all()[0]
        self.complete_task(task_2)
        task_3 = task_2.out_tasks.all()[0]

        self.assertEqual(Task.objects.count(), 3)
        self.assertEqual(len(task_3.responses), 2)
        self.assertEqual(task_3.responses["name"], task.responses["name"])
        self.assertEqual(task_3.responses["phone1"], task.responses["phone"])

    def test_copy_field_by_case_copy_all(self):
        self.initial_stage.json_schema = '{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}'
        self.initial_stage.save()
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage)
        )
        third_stage = second_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                json_schema='{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}',
                assign_user_from_stage=self.initial_stage)
        )
        CopyField.objects.create(
            copy_by=CopyFieldConstants.CASE,
            task_stage=third_stage,
            copy_from_stage=self.initial_stage,
            copy_all=True)

        task = self.create_initial_task()
        correct_responses = {"name": "kloop", "phone": 3, "addr": "kkkk"}
        task = self.complete_task(task, responses=correct_responses)
        task_2 = task.out_tasks.all()[0]
        self.complete_task(task_2)
        task_3 = task_2.out_tasks.all()[0]
        self.assertEqual(task_3.responses, task.responses)

    def test_copy_input(self):
        self.initial_stage.json_schema = '{"type": "object","properties": {"name": {"type": "string"},"phone": {"type": "integer"},"address": {"type": "string"}}}'
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(
            TaskStage(
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage,
                copy_input=True)
        )
        task = self.create_initial_task()
        correct_responses = {"name": "kloop", "phone": 3, "address": "kkkk"}
        task = self.complete_task(task, responses=correct_responses)
        task_2 = task.out_tasks.all()[0]

        self.assertEqual(task_2.responses, task.responses)

    def test_conditional_ping_pong_pass(self):
        self.initial_stage.json_schema = '{"type":"object","properties":{"answer":{"type":"string"}}}'
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )

        verification_task_stage = conditional_stage.add_stage(TaskStage(
            name="Verification task stage",
            json_schema='{"type":"object","properties":{"verified":{"type":"string"}}}'

        ))

        final_task_stage = verification_task_stage.add_stage(TaskStage(
            name="Final task stage",
            assign_user_from_stage=self.initial_stage,
            assign_user_by=TaskStageConstants.STAGE
        ))

        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        initial_task = self.update_task_responses(initial_task, {"answer": "something"})
        initial_task = self.complete_task(initial_task)

        verification_task = Task.objects \
            .get(stage=verification_task_stage, case=initial_task.case)

        verification_task = self.request_assignment(verification_task, verification_client)

        verification_task = self.complete_task(
            verification_task,
            {"verified": "yes"},
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)
        self.assertFalse(initial_task.reopened)

        self.assertTrue(verification_task.complete)

        self.assertEqual(Task.objects.count(), 3)

        final_task = Task.objects.get(case=initial_task.case, stage=final_task_stage)

        self.assertEqual(final_task.assignee, self.user)

    def test_conditional_ping_pong_copy_input_if_task_returned_again(self):
        self.initial_stage.json_schema = '{"type":"object","properties":{"answer":{"type":"string"}}}'
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )

        verification_task_stage = conditional_stage.add_stage(TaskStage(
            name="Verification task stage",
            json_schema='{"type":"object","properties":{"answer":{"type":"string"},"verified":{"type":"string"}}}',
            copy_input=True
        ))

        final_task_stage = verification_task_stage.add_stage(TaskStage(
            name="Final task stage",
            assign_user_from_stage=self.initial_stage,
            assign_user_by=TaskStageConstants.STAGE
        ))

        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        responses = {"answer": "something"}
        initial_task = self.update_task_responses(initial_task, responses)
        initial_task = self.complete_task(initial_task)

        verification_task = Task.objects \
            .get(stage=verification_task_stage, case=initial_task.case)

        verification_task = self.request_assignment(verification_task, verification_client)

        self.assertEqual(responses, verification_task.responses)

        verification_task.responses['verified'] = 'no'

        verification_task = self.complete_task(
            verification_task,
            verification_task.responses,
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.reopened)
        self.assertFalse(initial_task.complete)
        self.assertTrue(verification_task.complete)
        self.assertEqual(Task.objects.count(), 2)

        initial_task = self.complete_task(initial_task, {"answer": "something new"})

        verification_task = initial_task.out_tasks.get()

        self.assertEqual(verification_task.responses, {"answer": "something new", "verified": "no"})

        verification_task.responses['verified'] = 'yes'

        verification_task = self.complete_task(
            verification_task,
            verification_task.responses,
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)
        self.assertTrue(initial_task.reopened)

        self.assertTrue(verification_task.complete)

        self.assertEqual(Task.objects.count(), 3)

        final_task = Task.objects.get(case=initial_task.case, stage=final_task_stage)

        self.assertEqual(final_task.assignee, self.user)

    def test_conditional_ping_pong_doesnt_pass(self):
        self.initial_stage.json_schema = '{"type":"object","properties":{"answer":{"type":"string"}}}'
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )

        verification_task_stage = conditional_stage.add_stage(TaskStage(
            name="Verification task stage",
            json_schema='{"type":"object","properties":{"answer":{"type":"string"},"verified":{"type":"string"}}}'

        ))

        final_task_stage = verification_task_stage.add_stage(TaskStage(
            name="Final task stage",
            assign_user_from_stage=self.initial_stage,
            assign_user_by=TaskStageConstants.STAGE
        ))

        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, {"answer": "something"})

        verification_task = initial_task.out_tasks.get()

        verification_task = self.request_assignment(verification_task, verification_client)
        verification_task = self.complete_task(
            verification_task,
            {"verified": "no"},
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.reopened)
        self.assertFalse(initial_task.complete)
        self.assertTrue(verification_task.complete)
        self.assertEqual(Task.objects.count(), 2)

        initial_task = self.complete_task(initial_task, {"answer": "something new"})

        verification_task = initial_task.out_tasks.get()
        verification_task = self.complete_task(
            verification_task,
            {"verified": "yes"},
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)
        self.assertTrue(initial_task.reopened)
        self.assertTrue(verification_task.complete)
        self.assertEqual(Task.objects.count(), 3)

        final_task = Task.objects.get(case=initial_task.case, stage=final_task_stage)

        self.assertEqual(final_task.assignee, self.user)

    def test_notification_with_target_user(self):
        [Notification.objects.create(
            title=f"Hello world{i}",
            text="There are new chain for you",
            campaign=self.campaign,
            target_user=self.user
        )
            for i in range(5)]
        user_notifications = self.user.notifications.all().order_by('-created_at')

        for i in user_notifications[:2]:
            response = self.get_objects("notification-detail", pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.notifications.filter(notification_statuses__user=self.user).count(), 2)

        for i in user_notifications[:2]:
            response = self.get_objects("notification-detail", pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user_notifications.filter(notification_statuses__user=self.user).count(), 2)

        for i in user_notifications[:2]:
            response = self.get_objects("notification-open-notification", pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user_notifications.filter(notification_statuses__user=self.user).count(), 2)

        for i in user_notifications[2:]:
            response = self.get_objects("notification-open-notification", pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(user_notifications.filter(notification_statuses__user=self.user).count(), 5)

        for i in user_notifications[:2]:
            response = self.get_objects("notification-detail", client=self.employee_client, pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(NotificationStatus.objects.count(), 5)

    def test_notification_with_manager(self):
        notifications = [Notification.objects.create(
            title=f"Hello world{i}",
            text="There are new chain for you",
            campaign=self.campaign,
            target_user=self.user
        )
            for i in range(5)]
        self.employee.managed_campaigns.add(self.campaign)
        for i in notifications[:]:
            response = self.get_objects("notification-detail", client=self.employee_client, pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(notification_statuses__user=self.employee).count(), 5)
        self.employee.managed_campaigns.remove(self.campaign)
        self.assertEqual(NotificationStatus.objects.count(), 5)

    def test_notification_with_target_rank(self):
        ranks_notifications = [Notification.objects.create(
            title=f"Hello world{i}",
            text="There are new chain for you",
            campaign=self.campaign,
            rank=self.default_rank
        )
            for i in range(5)]

        self.assertFalse(self.default_rank in self.user.ranks.all())
        for i in ranks_notifications[:]:
            response = self.get_objects("notification-detail", client=self.employee_client, pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            Notification.objects.filter(rank=self.default_rank, notification_statuses__user=self.user).count(), 0)

        self.user.ranks.add(self.default_rank)
        for i in ranks_notifications[:]:
            response = self.get_objects("notification-detail", pk=i.id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Notification.objects.filter(rank=self.default_rank, notification_statuses__user=self.user).count(), 5)
        self.assertEqual(NotificationStatus.objects.count(), 5)

    def test_conditional_ping_pong_copy_field_if_task_returned_again(self):
        self.initial_stage.json_schema = '{"type":"object","properties":{"answer":{"type":"string"}}}'
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                conditions=[{"field": "verified", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )

        verification_task_stage = conditional_stage.add_stage(TaskStage(
            name="Verification task stage",
            json_schema='{"type":"object","properties":{"answerField":{"type":"string"}, "verified":{"enum":["yes", "no"],"type":"string"}}}'
        ))

        final_task_stage = verification_task_stage.add_stage(TaskStage(
            name="Final task stage",
            assign_user_from_stage=self.initial_stage,
            assign_user_by=TaskStageConstants.STAGE
        ))

        CopyField.objects.create(
            copy_by=CopyFieldConstants.CASE,
            task_stage=verification_task_stage,
            copy_from_stage=self.initial_stage,
            fields_to_copy="answer->answerField"
        )
        # returning
        return_notification = Notification.objects.create(
            title='Your task have been returned!',
            campaign=self.campaign
        )
        auto_notification_1 = AutoNotification.objects.create(
            trigger_stage=verification_task_stage,
            recipient_stage=self.initial_stage,
            notification=return_notification,
            go=AutoNotificationConstants.BACKWARD
        )

        complete_notification = Notification.objects.create(
            title='You have been complete task successfully!',
            campaign=self.campaign
        )
        auto_notification_2 = AutoNotification.objects.create(
            trigger_stage=verification_task_stage,
            recipient_stage=self.initial_stage,
            notification=complete_notification,
            go=AutoNotificationConstants.FORWARD
        )

        verification_client = self.prepare_client(verification_task_stage)

        initial_task = self.create_initial_task()
        initial_task = self.complete_task(initial_task, {"answer": "something"})

        verification_task = initial_task.out_tasks.get()
        verification_task = self.request_assignment(verification_task, verification_client)

        self.assertEqual({"answerField": "something"}, verification_task.responses)

        verification_task.responses['verified'] = 'no'

        verification_task = self.complete_task(
            verification_task,
            verification_task.responses,
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.reopened)
        self.assertFalse(initial_task.complete)
        self.assertTrue(verification_task.complete)
        self.assertEqual(Task.objects.count(), 2)
        user_notifications = Notification.objects.filter(target_user=self.user)
        self.assertEqual(user_notifications.count(), 1)
        self.assertEqual(user_notifications[0].title, return_notification.title)

        initial_task = self.complete_task(initial_task, {"answer": "something new"})

        verification_task = initial_task.out_tasks.get()
        self.assertEqual(verification_task.responses, {"answerField": "something new", "verified": "no"})

        verification_task.responses['verified'] = 'yes'
        verification_task = self.complete_task(
            verification_task,
            verification_task.responses,
            verification_client)

        initial_task = Task.objects.get(id=initial_task.id)

        self.assertTrue(initial_task.complete)
        self.assertTrue(initial_task.reopened)
        self.assertTrue(verification_task.complete)
        self.assertEqual(Task.objects.count(), 3)

        bw_notifications = self.user.notifications.filter(sender_task=verification_task,
                                                          receiver_task=initial_task,
                                                          trigger_go=AutoNotificationConstants.BACKWARD)
        fw_notifications = self.user.notifications.filter(sender_task=verification_task,
                                                          receiver_task=initial_task,
                                                          trigger_go=AutoNotificationConstants.FORWARD)
        self.assertEqual(self.user.notifications.count(), 2)
        self.assertEqual(bw_notifications.count(), 1)
        self.assertEqual(fw_notifications.count(), 1)
        self.assertEqual(bw_notifications[0].title, auto_notification_1.notification.title)
        self.assertEqual(fw_notifications[0].title, auto_notification_2.notification.title)

    def test_quiz(self):
        task_correct_responses = self.create_initial_task()
        correct_responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "d"}
        self.initial_stage.json_schema = {
            "type": "object",
            "properties": {
                "1": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 1", "type": "string"
                },
                "2": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 2", "type": "string"
                },
                "3": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 3", "type": "string"
                },
                "4": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 4", "type": "string"
                },
                "5": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 5", "type": "string"
                }
            },
            "dependencies": {},
            "required": ["1", "2", "3", "4", "5"]
        }
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses
        )
        task = self.create_initial_task()
        responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "b"}
        task = self.complete_task(task, responses=responses)

        self.assertEqual(task.responses[Quiz.SCORE], 80)
        self.assertEqual(Task.objects.count(), 2)
        self.assertTrue(task.complete)

    def test_quiz_correctly_answers(self):
        task_correct_responses = self.create_initial_task()

        self.initial_stage.json_schema = {
            "type": "object",
            "properties": {
                "q_1": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 1",
                    "type": "string"
                },
                "q_2": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 2",
                    "type": "string"
                },
                "q_3": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 3",
                    "type": "string"
                }
            },
            "dependencies": {},
            "required": [
                "q_1",
                "q_2",
                "q_3"
            ]
        }
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()

        correct_responses = {"q_1": "a", "q_2": "b", "q_3": "a"}
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            show_answer=Quiz.ShowAnswers.ALWAYS
        )
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)

        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], "Question 2\nQuestion 3")
        self.assertEqual(Task.objects.count(), 2)
        self.assertTrue(task.complete)

    def test_quiz_above_threshold(self):
        task_correct_responses = self.create_initial_task()
        correct_responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "d"}
        self.initial_stage.json_schema = {
            "type": "object",
            "properties": {
                "1": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 1", "type": "string"
                },
                "2": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 2", "type": "string"
                },
                "3": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 3", "type": "string"
                },
                "4": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 4", "type": "string"
                },
                "5": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 5", "type": "string"
                }
            },
            "dependencies": {},
            "required": ["1", "2", "3", "4", "5"]
        }
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()

        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            threshold=70
        )
        self.initial_stage.add_stage(
            TaskStage(
                assign_user_by="ST",
                assign_user_from_stage=self.initial_stage
            )
        )
        task = self.create_initial_task()
        responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "b"}
        task = self.complete_task(task, responses=responses)

        self.assertEqual(task.responses[Quiz.SCORE], 80)
        self.assertEqual(Task.objects.count(), 3)
        self.assertTrue(task.complete)

    def test_quiz_below_threshold(self):
        task_correct_responses = self.create_initial_task()
        correct_responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "d"}
        self.initial_stage.json_schema = {
            "type": "object",
            "properties": {
                "1": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 1", "type": "string"
                },
                "2": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 2", "type": "string"
                },
                "3": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 3", "type": "string"
                },
                "4": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 4", "type": "string"
                },
                "5": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 5", "type": "string"
                }
            },
            "dependencies": {},
            "required": ["1", "2", "3", "4", "5"]
        }
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            threshold=90
        )
        self.initial_stage.add_stage(
            TaskStage(
                assign_user_by="ST",
                assign_user_from_stage=self.initial_stage
            )
        )
        task = self.create_initial_task()
        responses = {"1": "a", "2": "b", "3": "a", "4": "c", "5": "b"}
        task = self.complete_task(task, responses=responses)

        self.assertEqual(task.responses[Quiz.SCORE], 80)
        self.assertEqual(Task.objects.count(), 2)
        self.assertFalse(task.complete)

    def test_quiz_show_answers_never(self):
        task_correct_responses = self.create_initial_task()

        js_schema = {
            "type": "object",
            "properties": {
                "q_1": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 1",
                    "type": "string"
                },
                "q_2": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 2",
                    "type": "string"
                },
                "q_3": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 3",
                    "type": "string"
                }
            },
            "dependencies": {},
            "required": [
                "q_1",
                "q_2",
                "q_3"
            ]
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        correct_responses = {"q_1": "a", "q_2": "b", "q_3": "a"}
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        task_correct_responses.assignee = None
        task_correct_responses.save()
        quiz = Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            show_answer=Quiz.ShowAnswers.NEVER
        )
        # Test answers if no threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 1)

        # Test answers if below threshold
        quiz.threshold = 50
        quiz.save()
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertFalse(task.complete)
        self.assertEqual(self.user.tasks.count(), 2)

        # Test answers if above threshold
        task = self.create_initial_task()
        responses = correct_responses
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 100)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 3)

    def test_quiz_show_answers_always(self):
        task_correct_responses = self.create_initial_task()

        js_schema = {
            "type": "object",
            "properties": {
                "q_1": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 1",
                    "type": "string"
                },
                "q_2": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 2",
                    "type": "string"
                },
                "q_3": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 3",
                    "type": "string"
                }
            },
            "dependencies": {},
            "required": [
                "q_1",
                "q_2",
                "q_3"
            ]
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        correct_responses = {"q_1": "a", "q_2": "b", "q_3": "a"}
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        task_correct_responses.assignee = None
        task_correct_responses.save()
        quiz = Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            show_answer=Quiz.ShowAnswers.ALWAYS
        )
        # Test answers if no threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS],
                         'Question 2\nQuestion 3')
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 1)

        # Test answers if below threshold
        quiz.threshold = 50
        quiz.save()
        task = self.create_initial_task()
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS],
                         'Question 2\nQuestion 3')
        self.assertFalse(task.complete)
        self.assertEqual(self.user.tasks.count(), 2)

        # Test answers if above threshold
        task = self.create_initial_task()
        responses = correct_responses
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 100)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], '')
        self.assertTrue(task.complete)

    def test_quiz_show_answers_on_pass(self):
        task_correct_responses = self.create_initial_task()

        js_schema = {
            "type": "object",
            "properties": {
                "q_1": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 1",
                    "type": "string"
                },
                "q_2": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 2",
                    "type": "string"
                },
                "q_3": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 3",
                    "type": "string"
                }
            },
            "dependencies": {},
            "required": [
                "q_1",
                "q_2",
                "q_3"
            ]
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        correct_responses = {"q_1": "a", "q_2": "b", "q_3": "a"}
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        task_correct_responses.assignee = None
        task_correct_responses.save()
        quiz = Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            show_answer=Quiz.ShowAnswers.ON_PASS
        )
        # Test answers if no threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 1)

        # Test answers if below threshold
        quiz.threshold = 50
        quiz.save()
        task = self.create_initial_task()
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertFalse(task.complete)
        self.assertEqual(self.user.tasks.count(), 2)

        # Test answers if above threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "b", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 66)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], 'Question 3')
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 3)

    def test_quiz_show_answers_on_fail(self):
        task_correct_responses = self.create_initial_task()

        js_schema = {
            "type": "object",
            "properties": {
                "q_1": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 1",
                    "type": "string"
                },
                "q_2": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 2",
                    "type": "string"
                },
                "q_3": {
                    "enum": ["a", "b", "c"],
                    "title": "Question 3",
                    "type": "string"
                }
            },
            "dependencies": {},
            "required": [
                "q_1",
                "q_2",
                "q_3"
            ]
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        correct_responses = {"q_1": "a", "q_2": "b", "q_3": "a"}
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        task_correct_responses.assignee = None
        task_correct_responses.save()
        quiz = Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses,
            show_answer=Quiz.ShowAnswers.ON_FAIL
        )
        # Test answers if no threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "c", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 1)

        # Test answers if below threshold
        quiz.threshold = 50
        quiz.save()
        task = self.create_initial_task()
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 33)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS],
                         'Question 2\nQuestion 3')
        self.assertFalse(task.complete)
        self.assertEqual(self.user.tasks.count(), 2)

        # Test answers if above threshold
        task = self.create_initial_task()
        responses = {"q_1": "a", "q_2": "b", "q_3": "c"}
        task = self.complete_task(task, responses=responses)
        self.assertEqual(task.responses[Quiz.SCORE], 66)
        self.assertEqual(task.responses[Quiz.INCORRECT_QUESTIONS], [])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 3)

    def test_delete_stage_assign_by_ST(self):
        second_stage = self.initial_stage.add_stage(TaskStage(
            name="second_stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage
        ))
        third_stage = second_stage.add_stage(TaskStage(
            name="third stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=second_stage
        ))

        self.assertEqual(TaskStage.objects.count(), 3)
        self.initial_stage.delete()
        self.assertEqual(TaskStage.objects.count(), 2)

    def test_response_flattener_list_wrong_not_manager(self):
        response = self.get_objects('responseflattener-list', client=self.client)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_response_flattener_list_happy(self):
        self.user.managed_campaigns.add(self.campaign)
        AdminPreference.objects.create(user=self.user, campaign=self.campaign)

        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage)

        response = self.get_objects('responseflattener-list', client=self.client)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_flattener_retrieve_wrong_not_manager(self):
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage)

        response = self.get_objects('responseflattener-detail', pk=response_flattener.id, client=self.client)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_response_flattener_retrieve_wrong_not_my_flattener(self):
        self.employee.managed_campaigns.add(self.campaign)
        AdminPreference.objects.create(user=self.employee, campaign=self.campaign)

        new_campaign = Campaign.objects.create(name="Another")
        self.user.managed_campaigns.add(new_campaign)

        AdminPreference.objects.create(user=self.user, campaign=self.campaign)

        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage)

        response = self.get_objects('responseflattener-detail', pk=response_flattener.id, client=self.client)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_response_flattener_retrieve_happy_my_flattener(self):
        self.user.managed_campaigns.add(self.campaign)
        AdminPreference.objects.create(user=self.user, campaign=self.campaign)

        response_flattener = ResponseFlattener.objects.create(
            task_stage=self.initial_stage
        )

        response = self.get_objects('responseflattener-detail', pk=response_flattener.id, client=self.client)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_flattener_create_wrong(self):
        resp_flattener = {'task_stage': self.initial_stage.id,}

        response = self.client.post(reverse('responseflattener-list'), data=resp_flattener)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_response_flattener_create_happy(self):
        self.user.managed_campaigns.add(self.campaign)
        AdminPreference.objects.create(user=self.user, campaign=self.campaign)

        resp_flattener = {'task_stage': self.initial_stage.id,}

        response = self.client.post(reverse('responseflattener-list'), data=resp_flattener)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_response_flattener_update_wrong(self):
        resp_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True)
        self.assertTrue(resp_flattener.copy_first_level)

        response = self.client.patch(reverse('responseflattener-detail', kwargs={"pk": resp_flattener.id}),
                                     data={"copy_first_level": False})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(resp_flattener.copy_first_level)

    def test_response_flattener_update_happy(self):
        self.user.managed_campaigns.add(self.campaign)
        AdminPreference.objects.create(user=self.user, campaign=self.campaign)

        resp_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True)

        response = self.client.patch(reverse('responseflattener-detail', kwargs={"pk": resp_flattener.id}),
                                     {"copy_first_level": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resp_flattener = ResponseFlattener.objects.get(id=resp_flattener.id)
        self.assertFalse(resp_flattener.copy_first_level)

    def test_response_flattener_create_row(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        row = {'id': task.id, 'column1': 'First', 'column2': 'SecondColumn', 'oik__(i)uik': 'SecondLayer'}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(i)uik"])

        task = self.complete_task(task, responses, self.client)

        flattener_row = response_flattener.flatten_response(task)
        self.assertEqual(row, flattener_row)

    def test_response_flattener_flatten_all(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"opening":{"15_c":{}, "16_c":{}, "17_c":{}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["opening"]}'
        self.initial_stage.save()

        answers = {"opening": {"15_c": "secured", "16_c": "no", "17_c": "no"}}
        task.responses = answers
        task.save()
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage,
                                                              flatten_all=True)

        result = response_flattener.flatten_response(task)
        self.assertEqual({"id": task.id, "opening__15_c": "secured", "opening__16_c": "no", "opening__17_c": "no"},
                         result)

    def test_response_flattener_regex_happy(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(r)uik[\d]{1,2}"])

        task = self.complete_task(task, responses, self.client)

        result = response_flattener.flatten_response(task)
        self.employee.managed_campaigns.add(self.campaign)
        answer = {"id": task.id, "column1": "First", "column2": "SecondColumn", "oik__(r)uik[\d]{1,2}": "SecondLayer"}

        self.assertEqual(answer, result)

    def test_response_flattener_regex_wrong(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(r)ui[\d]{1,2}"])

        task = self.complete_task(task, responses, self.client)

        result = response_flattener.flatten_response(task)
        self.employee.managed_campaigns.add(self.campaign)
        answer = {"id": task.id, "column1": "First", "column2": "SecondColumn"}

        self.assertEqual(answer, result)

    def test_get_response_flattener_success(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik__uik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(i)uik", "dfasdf", "dfasdfasd"])

        task = self.complete_task(task, responses, self.client)

        self.employee.managed_campaigns.add(self.campaign)
        new_client = self.create_client(self.employee)

        params = {"response_flattener": response_flattener.id, "stage": self.initial_stage.id}
        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_flattener_unique_success(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(i)uik"])
        response_flattener_second = ResponseFlattener.objects.get_or_create(task_stage=self.initial_stage)

        self.assertEqual(ResponseFlattener.objects.count(), 1)

        task = self.complete_task(task, responses, self.client)

        self.employee.managed_campaigns.add(self.campaign)
        new_client = self.create_client(self.employee)

        params = {"response_flattener": response_flattener.id, "stage": self.initial_stage.id}
        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_flattener_get_tasks_success(self):
        tasks = self.create_initial_tasks(5)

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, flatten_all=True)

        for i, t in enumerate(tasks):
            task = self.complete_task(t, responses, self.client)
            tasks[i] = task

        self.employee.managed_campaigns.add(self.campaign)
        new_client = self.create_client(self.employee)

        params = {"response_flattener": response_flattener.id}
        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        r = {"column2": "SecondColumn", "oik__uik1": "SecondLayer"}
        for t in tasks:
            r["id"] = t.id
            self.assertEqual(r, response_flattener.flatten_response(t))

    def test_get_response_flattener_copy_whole_response_success(self):
        task = self.create_task(self.initial_stage)

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column1": "First", "column2": "SecondColumn", "oik": {"uik1": {"uik1": [322, 123, 23]}}}
        task.responses = responses
        task.save()
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, flatten_all=True)

        result = {'id': task.id, 'column1': 'First', 'column2': 'SecondColumn', 'oik__uik1__uik1': [322, 123, 23]}
        self.assertEqual(response_flattener.flatten_response(task), result)

    def test_get_response_flattener_generate_file_url(self):

        task = self.create_task(self.initial_stage)
        self.initial_stage.ui_schema = '{"AAA":{"ui:widget":"customfile"},"ui:order": ["AAA"]}'
        self.initial_stage.json_schema = '{"properties":{"AAA": {"AAA":{}}}}'
        self.initial_stage.save()

        responses = {"AAA": '{"i":"public/img.jpg"}'}
        task.responses = responses
        task.save()
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, flatten_all=True)
        flattened_task = response_flattener.flatten_response(task)
        self.assertEqual(flattened_task, {"id": task.id,
                                          "AAA": "https://storage.cloud.google.com/gigaturnip-b6b5b.appspot.com/public/img.jpg?authuser=1"})

    def test_get_response_flattener_order_columns(self):

        task = self.create_task(self.initial_stage)
        self.initial_stage.ui_schema = '{"ui:order": [ "col2", "col3", "col1"]}'
        self.initial_stage.json_schema = '{"properties":{"col1": {"col1_1":{}}, "col2": {"col2_1":{}}, "col3": {"properties": {"d": {"properties": {"d": {}}}}}}}'
        self.initial_stage.save()

        responses = {"col1": "SecondColumn", "col2": "First", "col3": {"d": {"d": 122}}}
        task.responses = responses
        task.save()
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, flatten_all=True)

        ordered_columns = response_flattener.ordered_columns()
        self.assertEqual(ordered_columns, ["id", "col2", "col3__d__d", "col1"])

        # Testing system fields
        response_flattener.copy_system_fields = True
        response_flattener.save()
        ordered_columns = response_flattener.ordered_columns()
        system_columns = ["id", 'created_at', 'updated_at', 'assignee_id', 'stage_id', 'case_id',
                          'integrator_group', 'complete', 'force_complete', 'reopened',
                          'internal_metadata', 'start_period', 'end_period',
                          'schema', 'ui_schema']
        responses_fields = ["col2", "col3__d__d", "col1"]

        all_columns = system_columns + responses_fields
        self.assertEqual(ordered_columns, all_columns)
        flattened_task = response_flattener.flatten_response(task)
        for i in system_columns:
            self.assertEqual(task.__getattribute__(i), flattened_task[i])

    def test_response_flattener_with_previous_names(self):
        tasks = self.create_initial_tasks(5)
        self.employee.managed_campaigns.add(self.campaign)
        new_client = self.create_client(self.employee)

        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        responses = {"column2": "SecondColumn", "oik": {"uik1": "SecondLayer"}}
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, flatten_all=True)

        for i, t in enumerate(tasks[:3]):
            task = self.complete_task(t, responses, self.client)
            tasks[i] = task

        for i, t in enumerate(tasks[3:]):
            responses['another'] = "field not in schema"
            task = self.complete_task(t, responses, self.client)
            tasks[i + 3] = task

        params = {"response_flattener": response_flattener.id}
        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)
        columns = response.content.decode().split("\r\n", 1)[0].split(',')
        self.assertEqual(columns, ['id', 'column2', 'column1', 'oik__uik1', 'description'])

        response_flattener.columns = ['another']
        response_flattener.save()

        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)
        columns = response.content.decode().split("\r\n", 1)[0].split(',')
        self.assertEqual(columns, ['id', 'another', 'column2', 'column1', 'oik__uik1'])

    def test_get_response_flattener_fail(self):
        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(i)uik"])

        new_client = self.create_client(self.employee)
        params = {"response_flattener": response_flattener.id, "stage": self.initial_stage.id}
        response = self.get_objects("responseflattener-csv", params=params, client=new_client, pk=response_flattener.id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_response_flattener_not_found(self):

        response_flattener = ResponseFlattener.objects.create(task_stage=self.initial_stage, copy_first_level=True,
                                                              columns=["oik__(i)uik"])

        response = self.get_objects("responseflattener-csv", pk=response_flattener.id + 111)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_user_activity_csv_fail(self):
        self.create_initial_tasks(5)
        response = self.client.get(reverse('task-user-activity-csv') + "?csv=22")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_logs_for_task_stages(self):
        old_count = Log.objects.count()
        self.user.managed_campaigns.add(self.campaign)

        update_js = {"name": "Rename stage"}
        url = reverse("taskstage-detail", kwargs={"pk": self.initial_stage.id})
        response = self.client.patch(url, update_js)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(old_count, 0)
        self.assertEqual(Log.objects.count(), 1)

    def test_task_awards_count_is_equal(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "answer"
            ]
        })
        self.initial_stage.save()
        verification_task_stage = self.initial_stage.add_stage(TaskStage(
            name='verification',
            assign_user_by=TaskStageConstants.RANK
        ))
        verification_task_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "decision": {
                    "enum": ["reject", "pass"],
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "decision"
            ]
        })
        verification_task_stage.save()

        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=Rank.objects.get(name="Initial"))
        RankRecord.objects.create(
            user=self.user,
            rank=verifier_rank)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=verification_task_stage,
            rank=prize_rank,
            count=3,
            notification=notification
        )

        rank_l = RankLimit.objects.create(
            rank=verifier_rank,
            stage=verification_task_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True)

        for i in range(3):
            task = self.create_task(self.initial_stage, self.employee_client)
            task = self.complete_task(task, {"answer": "norm"}, self.employee_client)

            response_assign = self.get_objects("task-request-assignment", pk=task.out_tasks.all()[0].id)
            self.assertEqual(response_assign.status_code, status.HTTP_200_OK)
            task_to_check = Task.objects.get(assignee=self.user, case=task.case)
            task_to_check = self.complete_task(task_to_check, {"decision": "pass"}, client=self.client)

        employee_ranks = [i.rank for i in RankRecord.objects.filter(user=self.employee)]
        self.assertEqual(len(employee_ranks), 2)
        self.assertIn(prize_rank, employee_ranks)

        user_notifications = Notification.objects.filter(target_user=self.employee,
                                                         title=task_awards.notification.title)
        self.assertEqual(user_notifications.count(), 1)

    def test_task_awards_count_is_lower(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "answer"
            ]
        })
        self.initial_stage.save()

        verification_task_stage = self.initial_stage.add_stage(TaskStage(
            name='verification',
            assign_user_by=TaskStageConstants.RANK
        ))
        verification_task_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "decision": {
                    "enum": ["reject", "pass"],
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "decision"
            ]
        })
        verification_task_stage.save()

        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=Rank.objects.get(name="Initial"))
        RankRecord.objects.create(
            user=self.user,
            rank=verifier_rank)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=verification_task_stage,
            rank=prize_rank,
            count=3,
            notification=notification
        )

        rank_l = RankLimit.objects.create(
            rank=verifier_rank,
            stage=verification_task_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True)

        for i in range(2):
            task = self.create_task(self.initial_stage, self.employee_client)
            task = self.complete_task(task, {"answer": "norm"}, client=self.employee_client)

            response_assign = self.get_objects("task-request-assignment", {"decision": "pass"},
                                               pk=task.out_tasks.all()[0].id)
            self.assertEqual(response_assign.status_code, status.HTTP_200_OK)
            task_to_check = Task.objects.get(assignee=self.user, case=task.case)
            task_to_check = self.complete_task(task_to_check, {"decision": "pass"}, client=self.client)

        employee_ranks = [i.rank for i in RankRecord.objects.filter(user=self.employee)]
        self.assertEqual(len(employee_ranks), 1)
        self.assertNotIn(prize_rank, employee_ranks)

        user_notifications = Notification.objects.filter(target_user=self.employee,
                                                         title=task_awards.notification.title)
        self.assertEqual(user_notifications.count(), 0)

    def test_task_awards_count_many_task_stages(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "answer"
            ]
        })
        self.initial_stage.save()

        second_task_stage = self.initial_stage.add_stage(TaskStage(
            name='Second stage',
            json_schema=self.initial_stage.json_schema,
            assign_user_by="ST",
            assign_user_from_stage=self.initial_stage))
        verification_task_stage = second_task_stage.add_stage(TaskStage(
            name='verification',
            assign_user_by=TaskStageConstants.RANK
        ))
        verification_task_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "decision": {
                    "enum": ["reject", "pass"],
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "decision"
            ]
        })
        verification_task_stage.save()

        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=Rank.objects.get(name="Initial"))
        RankRecord.objects.create(
            user=self.user,
            rank=verifier_rank)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            campaign=self.campaign,
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!"
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=verification_task_stage,
            rank=prize_rank,
            count=3,
            notification=notification
        )

        rank_l = RankLimit.objects.create(
            rank=verifier_rank,
            stage=verification_task_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True)

        for i in range(3):
            task = self.create_task(self.initial_stage, self.employee_client)
            task = self.complete_task(task, {"answer": "norm"}, client=self.employee_client)
            task_2 = task.out_tasks.all()[0]
            task_2 = self.complete_task(task_2, {"answer": "norm2"}, client=self.employee_client)

            response_assign = self.get_objects("task-request-assignment", {"decision": "pass"},
                                               pk=task_2.out_tasks.all()[0].id)
            self.assertEqual(response_assign.status_code, status.HTTP_200_OK)
            task_to_check = Task.objects.get(assignee=self.user, case=task.case)
            task_to_check = self.complete_task(task_to_check, {"decision": "pass"}, client=self.client)

        employee_ranks = [i.rank for i in RankRecord.objects.filter(user=self.employee)]
        self.assertEqual(len(employee_ranks), 2)
        self.assertIn(prize_rank, employee_ranks)

        user_notifications = Notification.objects.filter(target_user=self.employee,
                                                         title=task_awards.notification.title)
        self.assertEqual(user_notifications.count(), 1)

    def test_datetime_sort_for_tasks(self):
        from datetime import datetime

        second_stage = self.initial_stage.add_stage(TaskStage(
            assign_user_by="RA"
        ))
        third_stage = second_stage.add_stage(TaskStage(
            assign_user_by="RA"
        ))
        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=verifier_rank)
        RankLimit.objects.create(
            rank=verifier_rank,
            stage=second_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True
        )
        RankLimit.objects.create(
            rank=verifier_rank,
            stage=third_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True
        )
        time_limit = datetime(year=2020, month=1, day=1)
        DatetimeSort.objects.create(
            stage=second_stage,
            start_time=time_limit
        )
        DatetimeSort.objects.create(
            stage=third_stage,
            end_time=time_limit
        )

        task1 = self.create_initial_task()
        task1 = self.complete_task(task1)
        task2 = task1.out_tasks.get()

        response = self.get_objects('task-user-selectable', client=self.employee_client)
        content = json.loads(response.content)
        self.assertEqual(len(content['results']), 1)
        self.assertEqual(content['results'][0]['id'], task2.id)

        response_assign = self.get_objects('task-request-assignment', pk=task2.id, client=self.employee_client)
        self.assertEqual(response_assign.status_code, status.HTTP_200_OK)
        self.assertEqual(self.employee.tasks.count(), 1)

        task2 = Task.objects.get(id=task2.id)
        task2 = self.complete_task(task2, client=self.employee_client)

        last_task = task2.out_tasks.get()

        response = self.get_objects('task-user-selectable', client=self.employee_client)
        content = json.loads(response.content)
        self.assertEqual(len(content['results']), 0)

        response_assign = self.get_objects('task-request-assignment', pk=last_task.id, client=self.employee_client)
        self.assertEqual(response_assign.status_code, status.HTTP_200_OK)

        last_task = Task.objects.get(id=last_task.id)
        self.complete_task(last_task, client=self.employee_client)

    def test_timer_for_tasks(self):
        second_stage = self.initial_stage.add_stage(TaskStage(
            assign_user_by="RA"
        ))
        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=verifier_rank)
        RankLimit.objects.create(
            rank=verifier_rank,
            stage=second_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True
        )
        DatetimeSort.objects.create(
            stage=second_stage,
            how_much=2,
            after_how_much=0.1
        )
        task1 = self.create_initial_task()
        task1 = self.complete_task(task1)
        task1.out_tasks.get()

        response = self.get_objects('task-user-selectable', client=self.employee_client)
        content = json.loads(response.content)
        self.assertEqual(len(content['results']), 0)

    def test_task_with_timer_is_exist(self):
        second_stage = self.initial_stage.add_stage(TaskStage(
            assign_user_by="RA"
        ))
        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=verifier_rank)
        RankLimit.objects.create(
            rank=verifier_rank,
            stage=second_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True
        )
        DatetimeSort.objects.create(
            stage=second_stage,
            how_much=2,
            after_how_much=0.1
        )
        task1 = self.create_initial_task()
        task1 = self.complete_task(task1)
        task1.out_tasks.get()

        response = self.get_objects('task-user-relevant')
        content = json.loads(response.content)
        self.assertEqual(len(content['results']), 1)

    def test_test_webhook(self):
        task = self.create_initial_task()

        self.initial_stage.json_schema = '{"type": "object","required": ["first_term","second_term"],"properties": {"first_term": {"type": "integer","title": "First term"},"second_term": {"type": "integer","title": "Second term"}}}'
        self.initial_stage.save()
        second_stage = self.initial_stage.add_stage(TaskStage(
            name="Second",
            x_pos=1,
            y_pos=1,
        ))
        webhook = Webhook.objects.create(
            task_stage=second_stage,
            url='https://us-central1-journal-bb5e3.cloudfunctions.net/for_test_webhook',
        )
        expected_task = Task.objects.create(
            stage_id=second_stage.id,
            responses={'sum': 3}
        )

        responses = {"first_term": 1, "second_term": 2}

        task = self.complete_task(task, responses)
        task2 = task.out_tasks.get()
        self.assertEqual(task2.responses, expected_task.responses)

    def test_task_awards_for_giving_ranks(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "answer"
            ]
        })
        self.initial_stage.save()
        conditional_stage = ConditionalStage()
        conditional_stage.conditions = [{"field": "answer", "type": "string", "value": "norm", "condition": "=="}]
        conditional_stage = self.initial_stage.add_stage(conditional_stage)
        verification_task_stage = conditional_stage.add_stage(TaskStage(
            name='verification',
            assign_user_by="AU"
        ))
        verification_task_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "decision": {
                    "enum": ["reject", "pass"],
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "decision"
            ]
        })
        verification_task_stage.save()

        verifier_rank = Rank.objects.create(name="verifier")
        RankRecord.objects.create(
            user=self.employee,
            rank=Rank.objects.get(name="Initial"))
        RankRecord.objects.create(
            user=self.user,
            rank=verifier_rank)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=verification_task_stage,
            rank=prize_rank,
            count=3,
            notification=notification
        )

        rank_l = RankLimit.objects.create(
            rank=verifier_rank,
            stage=verification_task_stage,
            open_limit=5,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True)

        for i in range(3):
            task = self.create_task(self.initial_stage, self.employee_client)
            task = self.complete_task(task, {"answer": "norm"}, self.employee_client)

        employee_ranks = [i.rank for i in RankRecord.objects.filter(user=self.employee)]
        self.assertEqual(len(employee_ranks), 2)
        self.assertIn(prize_rank, employee_ranks)

        user_notifications = Notification.objects.filter(target_user=self.employee,
                                                         title=task_awards.notification.title)
        self.assertEqual(user_notifications.count(), 1)

    def test_task_stage_get_schema_fields(self):
        self.initial_stage.json_schema = '{"properties":{"column1":{"column1":{}},"column2":{"column2":{}},"oik":{"properties":{"uik1":{}}}}}'
        self.initial_stage.ui_schema = '{"ui:order": ["column2", "column1", "oik"]}'
        self.initial_stage.save()

        response = self.get_objects('taskstage-schema-fields', pk=self.initial_stage.id)
        self.assertEqual(response.data['fields'], ['column2', 'column1', 'oik__uik1'])

    def test_user_activity_on_stages(self):
        tasks = self.create_initial_tasks(5)
        self.user.managed_campaigns.add(self.campaign)

        ranks = [i['id'] for i in self.initial_stage.ranks.all().values('id')]
        in_stages = [i['id'] for i in
                     self.initial_stage.in_stages.all().values('id')]
        out_stages = [i['id'] for i in
                      self.initial_stage.out_stages.all().values('id')]
        # todo: add field 'users' to remove bug
        expected_activity = {
            'stage': self.initial_stage.id,
            'stage_name': self.initial_stage.name,
            'chain': self.initial_stage.chain.id,
            'chain_name': self.initial_stage.chain.name,
            'ranks': ranks or [None],
            'in_stages': in_stages or [None],
            'out_stages': out_stages or [None],
            'complete_true': 3,
            'complete_false': 2,
            'force_complete_false': 5,
            'force_complete_true': 0,
            'count_tasks': 5
        }

        if not expected_activity['in_stages']:
            expected_activity['in_stages'] = [None]
        if not expected_activity['out_stages']:
            expected_activity['out_stages'] = [None]

        for t in tasks[:3]:
            t.complete = True
            t.save()
        response = self.get_objects('task-user-activity')
        # Will Fail if your database isn't postgres. because of dj.func ArrayAgg. Make sure that your DB is PostgreSql
        self.assertEqual(
            json.loads(response.content)['results'], [expected_activity]
        )

    def test_post_json_filter_json_fields(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "name": {
                    "type": "string"
                },
                "age": {
                    "type": "integer"
                }
            }
        })
        self.initial_stage.ui_schema = '{"ui:order": ["name", "age"]}'
        self.initial_stage.save()
        second_stage = self.initial_stage.add_stage(TaskStage())
        self.client = self.prepare_client(second_stage, self.user)

        tasks = self.create_initial_tasks(5)
        names = ['Artur', 'Karim', 'Atai', 'Xakim', 'Rinat']

        i = 1
        for t, n in zip(tasks, names):
            self.complete_task(t, {"name": n, "age": 10 * i})
            i += 1

        post_data = {
            "items_conditions": [
                {
                    "conditions": [
                        {
                            "operator": "<=",
                            "value": "20"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
            ],
            "stage": self.initial_stage.id,
            "search_stage": second_stage.id

        }

        response = self.client.post(reverse("task-user-selectable") + '?responses_filter_values=Yes', data=post_data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)

        post_data = {
            "items_conditions": [
                {
                    "conditions": [
                        {
                            "operator": "<",
                            "value": "20"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
            ],
            "stage": self.initial_stage.id,
            "search_stage": second_stage.id

        }

        response = self.client.post(reverse("task-user-selectable") + '?responses_filter_values=Yes', data=post_data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

        post_data = {
            "items_conditions": [
                {
                    "conditions": [
                        {
                            "operator": "<=",
                            "value": "50"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
            ],
            "stage": self.initial_stage.id,
            "search_stage": second_stage.id

        }

        response = self.client.post(reverse("task-user-selectable") + '?responses_filter_values=Yes', data=post_data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 5)

        post_data = {
            "items_conditions": [
                {
                    "conditions": [
                        {
                            "operator": "<=",
                            "value": "50"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
                {
                    "conditions": [
                        {
                            "operator": ">",
                            "value": "20"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                }
            ],
            "stage": self.initial_stage.id,
            "search_stage": second_stage.id

        }

        response = self.client.post(reverse("task-user-selectable") + '?responses_filter_values=Yes', data=post_data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 3)
        post_data = {
            "items_conditions": [
                {
                    "conditions": [
                        {
                            "operator": "<=",
                            "value": "50"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
                {
                    "conditions": [
                        {
                            "operator": ">",
                            "value": "20"
                        }
                    ],
                    "field": "age",
                    "type": "integer"
                },
                {
                    "conditions": [
                        {
                            "operator": "in",
                            "value": "t"
                        }
                    ],
                    "field": "name",
                    "type": "string"
                }
            ],
            "stage": self.initial_stage.id,
            "search_stage": second_stage.id

        }

        response = self.client.post(reverse("task-user-selectable") + '?responses_filter_values=Yes', data=post_data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)

    def test_answers_validation(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "year": {"type": "number"},
                "name": {"type": "string"},
            },
            "required": ['price', 'name']
        })
        self.initial_stage.save()

        task = self.create_initial_task()
        response = self.complete_task(task, {'price': 'there must be digit',
                                             'year': 'there must be digit',
                                             'name': 'Kloop'}
                                      )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(json.loads(response.content)['pass'], ["properties", "price", "type"])

    def test_dynamic_json_schema_related_fields(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                },
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                }
            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ['time'],
            "count": 2
        }
        dynamic_json = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_json
        )

        task1 = self.create_initial_task()
        responses1 = {'weekday': weekdays[0], 'time': time_slots[0]}
        task1 = self.complete_task(task1, responses1)

        task2 = self.create_initial_task()
        task2 = self.complete_task(task2, responses1)

        task3 = self.create_initial_task()
        responses3 = {'weekday': weekdays[0]}

        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses3)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_schema = json.loads(js_schema)
        del updated_schema['properties']['time']['enum'][0]
        self.assertEqual(response.data['schema'], updated_schema)

        responses3['weekday'] = weekdays[1]
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses3)})
        updated_schema = json.loads(js_schema)
        self.assertEqual(response.data['schema'], updated_schema)

    def test_dynamic_json_schema_single_field(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                }
            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": [],
            "count": 2
        }
        dynamic_json = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_json
        )

        responses1 = {'weekday': weekdays[0]}

        task1 = self.create_initial_task()
        task1 = self.complete_task(task1, responses1)

        task2 = self.create_initial_task()
        task2 = self.complete_task(task2, responses1)

        task3 = self.create_initial_task()
        responses3 = {'weekday': weekdays[0]}

        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses3)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_schema = json.loads(js_schema)
        del updated_schema['properties']['weekday']['enum'][0]
        self.assertEqual(response.data['schema'], updated_schema)

        responses3['weekday'] = weekdays[1]
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses3)})
        self.assertEqual(response.data['schema'], updated_schema)

    def test_dynamic_json_schema_related_fields_from_another_stage(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']

        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                }
            }
        })
        self.initial_stage.save()

        json_schema_time = json.dumps({
            "type": "object",
            "properties": {
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                }
            }
        })
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Complete time',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage,
                json_schema=json_schema_time,
                ui_schema=json.dumps({"ui:order": ["time"]})
            )
        )

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ['time'],
            "count": 1
        }
        dynamic_json = DynamicJson.objects.create(
            source=self.initial_stage,
            target=second_stage,
            dynamic_fields=dynamic_fields_json
        )

        responses = {'weekday': weekdays[0]}
        for i in range(3):
            t = self.create_initial_task()
            t = self.complete_task(t, responses)
            self.complete_task(t.out_tasks.get(), {'time': time_slots[i]})

        t2 = self.create_initial_task()
        t2 = self.complete_task(t2, responses)
        t2_next = t2.out_tasks.get()
        response = self.get_objects('taskstage-load-schema-answers', pk=second_stage.id,
                                    params={"current_task": t2_next.id})
        updated_schema = json.loads(second_stage.json_schema)
        del updated_schema['properties']['time']['enum'][0]
        del updated_schema['properties']['time']['enum'][0]
        del updated_schema['properties']['time']['enum'][0]
        self.assertEqual(response.data['schema'], updated_schema)
        t2_next = self.complete_task(t2_next, {'time': time_slots[3]})

        t3 = self.create_initial_task()
        t3 = self.complete_task(t3, {'weekday': weekdays[1]})
        t3_next = t3.out_tasks.get()
        response = self.get_objects('taskstage-load-schema-answers', pk=second_stage.id,
                                    params={"current_task": t3_next.id})

        updated_schema = json.loads(second_stage.json_schema)
        self.assertEqual(response.data['schema'], updated_schema)

    def test_dynamic_json_schema_related_fields_from_another_stage(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']

        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                }
            }
        })
        self.initial_stage.save()

        json_schema_time = json.dumps({
            "type": "object",
            "properties": {
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                }
            }
        })
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Complete time',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage,
                json_schema=json_schema_time,
                ui_schema=json.dumps({"ui:order": ["time"]})
            )
        )

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ['time'],
            "constants": {
                "main": {},
                "foreign": {
                    "time": ["10:00"]
                }
            },
            "count": 1
        }
        dynamic_json = DynamicJson.objects.create(
            source=self.initial_stage,
            target=second_stage,
            dynamic_fields=dynamic_fields_json
        )

        responses = {'weekday': weekdays[0]}
        for i in range(3):
            t = self.create_initial_task()
            t = self.complete_task(t, responses)
            self.complete_task(t.out_tasks.get(), {'time': time_slots[i]})

        t2 = self.create_initial_task()
        t2 = self.complete_task(t2, responses)
        t2_next = t2.out_tasks.get()
        response = self.get_objects('taskstage-load-schema-answers', pk=second_stage.id,
                                    params={"current_task": t2_next.id})
        updated_schema = json.loads(second_stage.json_schema)
        del updated_schema['properties']['time']['enum'][1]
        del updated_schema['properties']['time']['enum'][1]
        self.assertIn("10:00", response.data['schema']['properties']['time']['enum'])

    def test_dynamic_json_schema_single_unique_field(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                }

            }
        })
        ui_schema = json.dumps({"ui:order": ["weekday"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_weekday = {
            "main": "weekday",
            "foreign": [],
            "count": 2
        }
        dynamic_json_weekday = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_weekday
        )

        responses1 = {'weekday': weekdays[0]}

        task1 = self.create_initial_task()
        task1 = self.complete_task(task1, responses1)

        task2 = self.create_initial_task()
        task2 = self.complete_task(task2, responses1)

        task3 = self.create_initial_task()
        responses3 = {'weekday': weekdays[0]}

        updated_schema = json.loads(js_schema)
        del updated_schema['properties']['weekday']['enum'][0]
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['schema'], updated_schema)

        response = self.complete_task(task3, responses3)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'][0], 'Your answers are non-compliance with the standard')
        self.assertEqual(response.data['pass'], ['properties', 'weekday', 'enum'])

    def test_dynamic_json_schema_related_unique_fields(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                },
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                }
            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ['time'],
            "count": 1
        }
        dynamic_json = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_json
        )

        for t in time_slots:
            task = self.create_initial_task()
            responses = {'weekday': weekdays[0], 'time': t}
            self.complete_task(task, responses)

        task = self.create_initial_task()

        responses = {'weekday': weekdays[0]}
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_schema = json.loads(js_schema)
        updated_schema['properties']['time']['enum'] = []
        self.assertEqual(response.data['schema'], updated_schema)

        responses = {'weekday': weekdays[1]}
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_schema = json.loads(js_schema)
        self.assertEqual(response.data['schema'], updated_schema)

    def test_dynamic_json_schema_three_foreign(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']
        doctors = ['Rinat', 'Aizirek', 'Aigerim', 'Beka']
        alphabet = ['a', 'b', 'c', 'd']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                },
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                },
                "doctor": {
                    "type": "string",
                    "title": "Which doctor",
                    "enum": doctors
                },
                "alphabet": {
                    "type": "string",
                    "title": "Which doctor",
                    "enum": alphabet
                }
            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ["time", "doctor", "alphabet"],
            "count": 1
        }
        dynamic_json = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_json
        )

        task = self.create_initial_task()
        responses = {'weekday': weekdays[0], 'time': time_slots[0], 'doctor': doctors[0], 'alphabet': alphabet[0]}
        self.complete_task(task, responses)

        task = self.create_initial_task()
        responses = {'weekday': weekdays[0], 'time': time_slots[0], 'doctor': doctors[0]}
        updated_schema = json.loads(js_schema)
        del updated_schema['properties']['alphabet']['enum'][0]
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})

        self.assertEqual(response.data['schema'], updated_schema)

        responses = {'weekday': weekdays[0], 'time': time_slots[0], 'doctor': doctors[1]}
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})
        updated_schema = json.loads(js_schema)
        self.assertEqual(response.data['schema'], updated_schema)

        responses = {'weekday': weekdays[1], 'time': time_slots[0], 'doctor': doctors[0]}
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})
        updated_schema = json.loads(js_schema)
        self.assertEqual(response.data['schema'], updated_schema)

        responses = {'weekday': weekdays[0], 'time': time_slots[1], 'doctor': doctors[0]}
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses)})
        updated_schema = json.loads(js_schema)
        self.assertEqual(response.data['schema'], updated_schema)

    def test_dynamic_json_schema_many(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        day_parts = ['12:00 - 13:00', '13:00 - 14:00', '14:00 - 15:00']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                },
                "day_part": {
                    "type": "string",
                    "title": "Select part of the day",
                    "enum": day_parts
                },

            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_weekday = {
            "main": "weekday",
            "foreign": [],
            "count": 2
        }
        dynamic_json_weekday = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_weekday
        )

        dynamic_fields_day_parts = {
            "main": "day_part",
            "foreign": [],
            "count": 2
        }
        dynamic_json_day_part = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_day_parts
        )

        responses1 = {'weekday': weekdays[0], 'day_part': day_parts[0]}

        task1 = self.create_initial_task()
        task1 = self.complete_task(task1, responses1)

        task2 = self.create_initial_task()
        task2 = self.complete_task(task2, responses1)

        task3 = self.create_initial_task()
        responses3 = {'weekday': weekdays[0], 'day_part': day_parts[0]}

        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_schema = json.loads(js_schema)
        del updated_schema['properties']['weekday']['enum'][0]
        del updated_schema['properties']['day_part']['enum'][0]
        self.assertEqual(response.data['schema'], updated_schema)

        responses3['weekday'] = weekdays[1]
        response = self.get_objects('taskstage-load-schema-answers', pk=self.initial_stage.id,
                                    params={'responses': json.dumps(responses3)})
        self.assertEqual(response.data['schema'], updated_schema)

    def test_update_taskstage(self):
        external_metadata = {"field": "value"}
        self.initial_stage.external_metadata = external_metadata
        self.initial_stage.save()
        response = self.get_objects('taskstage-detail', pk=self.initial_stage.id)
        self.assertEqual(response.data['external_metadata'], external_metadata)

    def test_dynamic_json_schema_try_to_complete_occupied_answer(self):
        weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
        time_slots = ['10:00', '11:00', '12:00', '13:00', '14:00']
        js_schema = json.dumps({
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": weekdays
                },
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": time_slots
                }
            }
        })
        ui_schema = json.dumps({"ui:order": ["time"]})
        self.initial_stage.json_schema = js_schema
        self.initial_stage.ui_schema = ui_schema
        self.initial_stage.save()

        dynamic_fields_json = {
            "main": "weekday",
            "foreign": ['time'],
            "count": 1
        }
        dynamic_json = DynamicJson.objects.create(
            target=self.initial_stage,
            dynamic_fields=dynamic_fields_json
        )

        task = self.create_initial_task()
        responses = {'weekday': weekdays[0], 'time': time_slots[0]}
        self.complete_task(task, responses)

        task = self.create_initial_task()

        responses = {'weekday': weekdays[0], 'time': time_slots[0]}
        response = self.complete_task(task, responses)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        responses['time'] = time_slots[1]
        task = self.complete_task(task, responses)
        self.assertEqual(task.responses, responses)

    def test_dynamic_json_obtain_options_from_stages(self):
        tasks_to_complete = self.create_initial_tasks(5)
        tasks_in_completion = self.create_initial_tasks(3)
        i = 5
        completed = []
        for t in tasks_to_complete:
            completed.append(self.complete_task(t, {"name": f"Person #{i}"}))
            i -= 1

        in_progress = []
        for t in tasks_in_completion:
            in_progress.append(self.update_task_responses(t, {"name": f"Person #{i}"}))
            i += 1


        new_chain = Chain.objects.create(
            name='Persons names chain',
            campaign=self.campaign
        )
        choose_name_stage = TaskStage.objects.create(
            name='Choose name',
            chain=new_chain,
            x_pos=1,
            y_pos=1,
            is_creatable=True,
            json_schema='{"type": "object","properties": {"choose_name": {"type": "string", "enum":[]}}}'
        )
        RankLimit.objects.create(
            open_limit=0,
            total_limit=0,
            is_creation_open=True,
            rank=self.user.ranks.all()[0],
            stage=choose_name_stage
        )

        dynamic_fields = {
            "main": "name",
            "foreign": ["choose_name"],

        }
        DynamicJson.objects.create(
            source=self.initial_stage,
            target=choose_name_stage,
            dynamic_fields=dynamic_fields,
            obtain_options_from_stage=True
        )

        task = self.create_task(choose_name_stage)
        response = self.get_objects('taskstage-load-schema-answers', pk=choose_name_stage.id,
                                    params={"current_task":task.id})
        updated_enums = response.data['schema']['properties']['choose_name']['enum']
        self.assertEqual(len(updated_enums), 5)
        self.assertEqual(['Person #1', 'Person #2', 'Person #3', 'Person #4', 'Person #5'], updated_enums)
        right_return = {
            'status': 200,
            'schema': {
                'type': 'object',
                'properties': {
                    'choose_name': {
                        'type': 'string',
                        'enum': ['Person #1', 'Person #2', 'Person #3', 'Person #4', 'Person #5']
                    }
                }
            }
        }

        self.assertEqual(right_return, response.data)

    def test_case_info_for_map(self):
        json_schema = {
            "type": "object",
            "properties": {
                "weekday": {
                    "type": "string",
                    "title": "Select Weekday",
                    "enum": ["mon", "tue", "wed", "thu", "fri"]
                },
                "time": {
                    "type": "string",
                    "title": "What time",
                    "enum": ["10:00", "11:00", "12:00", "13:00", "14:00"]
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(json_schema)
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Second Task Stage',
                json_schema=self.initial_stage.json_schema,
                assign_user_by='ST',
                assign_user_from_stage=self.initial_stage,
            )
        )

        responses = {"weekday": "mon", "time": "10:00"}
        task = self.create_initial_task()
        self.complete_task(task, responses)

        response = self.get_objects("case-info-by-case", pk=task.case.id)
        maps_info = [
            {'stage': self.initial_stage.id, 'stage__name': self.initial_stage.name, 'complete': [True],
             'force_complete': [False], 'id': [task.id]},
            {'stage': second_stage.id, 'stage__name': second_stage.name, 'complete': [False], 'force_complete': [False],
             'id': [task.out_tasks.get().id]}
        ]

        self.assertEqual(status.HTTP_200_OK, response.data['status'])
        for i in maps_info:
            self.assertIn(i, response.data['info'])

    def test_chain_get_graph(self):
        self.user.managed_campaigns.add(self.campaign)
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Second Task Stage',
                assign_user_by='ST',
                assign_user_from_stage=self.initial_stage,
            )
        )
        cond_stage = second_stage.add_stage(
            ConditionalStage(
                name="MyCondStage",
                conditions=[{"field": "foo", "value": "boo", "condition": "=="}]
            )
        )

        info_about_graph = [
            {'pk': self.initial_stage.id, 'name': self.initial_stage.name, 'in_stages': [None],
             'out_stages': [second_stage.id]},
            {'pk': second_stage.id, 'name': second_stage.name, 'in_stages': [self.initial_stage.id],
             'out_stages': [cond_stage.id]},
            {'pk': cond_stage.id, 'name': cond_stage.name, 'in_stages': [second_stage.id], 'out_stages': [None]}
        ]

        response = self.get_objects("chain-get-graph", pk=self.chain.id)
        self.assertEqual(len(response.data), 3)
        for i in info_about_graph:
            self.assertIn(i, response.data)

    def test_assign_by_previous_manual_user_without_rank(self):
        js_schema = {
            "type": "object",
            "properties": {
                "email_field": {
                    "type": "string",
                    "title": "email to assign",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage_schema = {
            "type": "object",
            "properties": {
                "foo": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Second stage',
                assign_user_by=TaskStageConstants.PREVIOUS_MANUAL,
                json_schema=json.dumps(second_stage_schema)
            )
        )

        PreviousManual.objects.create(
            field=["email_field"],
            task_stage_to_assign=second_stage,
            task_stage_email=self.initial_stage,
        )

        responses = {"email_field": "employee@email.com"}
        task = self.create_initial_task()
        bad_response = self.complete_task(task, responses)

        self.assertEqual(bad_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad_response.data['message'], 'User is not in the campaign.')

    def test_assign_by_previous_manual_user_with_rank_of_campaign(self):
        js_schema = {
            "type": "object",
            "properties": {
                "email_field": {
                    "type": "string",
                    "title": "email to assign",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage_schema = {
            "type": "object",
            "properties": {
                "foo": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Second stage',
                assign_user_by=TaskStageConstants.PREVIOUS_MANUAL,
                json_schema=json.dumps(second_stage_schema)
            )
        )

        PreviousManual.objects.create(
            field=["email_field"],
            task_stage_to_assign=second_stage,
            task_stage_email=self.initial_stage,
        )

        campaign_rank = RankLimit.objects.filter(stage__chain__campaign_id=self.campaign)[0].rank
        self.employee.ranks.add(campaign_rank)

        responses = {"email_field": "employee@email.com"}
        task = self.create_initial_task()
        task = self.complete_task(task, responses)

        new_task = Task.objects.get(stage=second_stage, case=task.case)

        self.assertEqual(new_task.assignee, CustomUser.objects.get(email='employee@email.com'))

    def test_assign_by_previous_manual_conditional_previous_happy(self):
        js_schema = {
            "type": "object",
            "properties": {
                "email_field": {
                    "type": "string",
                    "title": "email to assign",
                },
                'foo': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "=="}]
        ))

        final_stage_schema = {
            "type": "object",
            "properties": {
                "foo": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }
        final_stage = conditional_stage.add_stage(
            TaskStage(
                name='Final stage',
                assign_user_by=TaskStageConstants.PREVIOUS_MANUAL,
                json_schema=json.dumps(final_stage_schema)
            )
        )

        PreviousManual.objects.create(
            field=["email_field"],
            task_stage_to_assign=final_stage,
            task_stage_email=self.initial_stage,
        )

        campaign_rank = RankLimit.objects.filter(stage__chain__campaign_id=self.campaign)[0].rank
        self.employee.ranks.add(campaign_rank)

        responses = {"email_field": "employee@email.com", "foo": "boo"}
        task = self.create_initial_task()
        task = self.complete_task(task, responses)
        new_task = Task.objects.get(stage=final_stage, case=task.case)

        self.assertEqual(new_task.assignee, CustomUser.objects.get(email='employee@email.com'))

    def test_assign_by_previous_manual_conditional_previous_wrong_no_rank(self):
        js_schema = {
            "type": "object",
            "properties": {
                "email_field": {
                    "type": "string",
                    "title": "email to assign",
                },
                'foo': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "=="}]
        ))

        final_stage_schema = {
            "type": "object",
            "properties": {
                "foo": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }
        final_stage = conditional_stage.add_stage(
            TaskStage(
                name='Final stage',
                assign_user_by=TaskStageConstants.PREVIOUS_MANUAL,
                json_schema=json.dumps(final_stage_schema)
            )
        )

        PreviousManual.objects.create(
            field=["email_field"],
            task_stage_to_assign=final_stage,
            task_stage_email=self.initial_stage,
        )

        responses = {"email_field": "employee@email.com", "foo": "boo"}
        task = self.create_initial_task()
        bad_response = self.complete_task(task, responses)

        task = Task.objects.get(id=task.id)

        self.assertEqual(bad_response.data['message'], 'User is not in the campaign.')
        self.assertTrue(task.reopened)
        self.assertFalse(task.complete)
        self.assertEqual(Task.objects.count(), 1)

    def test_assign_by_previous_manual_conditional_previous_wrong_user_does_not_exist(self):
        js_schema = {
            "type": "object",
            "properties": {
                "email_field": {
                    "type": "string",
                    "title": "email to assign",
                },
                'foo': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        conditional_stage = self.initial_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "=="}]
        ))

        final_stage_schema = {
            "type": "object",
            "properties": {
                "foo": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }
        final_stage = conditional_stage.add_stage(
            TaskStage(
                name='Final stage',
                assign_user_by=TaskStageConstants.PREVIOUS_MANUAL,
                json_schema=json.dumps(final_stage_schema)
            )
        )

        PreviousManual.objects.create(
            field=["email_field"],
            task_stage_to_assign=final_stage,
            task_stage_email=self.initial_stage,
        )

        responses = {"email_field": "employe@email.com", "foo": "boo"}
        task = self.create_initial_task()
        bad_response = self.complete_task(task, responses)

        task = Task.objects.get(id=task.id)

        self.assertEqual(bad_response.data['message'], 'User employe@email.com doesn\'t exist.')
        self.assertTrue(task.reopened)
        self.assertFalse(task.complete)
        self.assertEqual(Task.objects.count(), 1)

    def create_cyclic_chain(self):
        js_schema = {
            "type": "object",
            "properties": {
                'name': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage_schema = {
            "type": "object",
            "properties": {
                'foo': {
                    "type": "string",
                }
            }
        }

        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name="Test pronunciation",
                json_schema=json.dumps(second_stage_schema),
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage
            )
        )

        conditional_stage = second_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "=="}]
        ))

        conditional_stage_cyclic = second_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "!="}]
        ))

        final_stage_schema = {
            "type": "object",
            "properties": {
                "too": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }

        final_stage = conditional_stage.add_stage(
            TaskStage(
                name='Final stage',
                assign_user_by=TaskStageConstants.STAGE,
                json_schema=json.dumps(final_stage_schema)
            )
        )

        conditional_stage_cyclic.out_stages.add(second_stage)
        conditional_stage_cyclic.save()

        return second_stage, conditional_stage, conditional_stage_cyclic, final_stage

    def test_cyclic_chain_ST(self):
        second_stage, conditional_stage, conditional_stage_cyclic, final_stage = self.create_cyclic_chain()

        task = self.create_initial_task()
        task = self.complete_task(task, {"name": "Kloop"})

        second_task_1 = task.out_tasks.get()
        second_task_1 = self.complete_task(second_task_1, {"foo": "not right"})
        self.assertEqual(Task.objects.filter(case=task.case).count(), 3)
        self.assertEqual(Task.objects.filter(case=task.case, stage=second_stage).count(), 2)

        second_task_2 = second_task_1.out_tasks.get()

        response = self.get_objects('case-info-by-case', pk=task.case.id)
        info_by_case = [
            {'stage': self.initial_stage.id, 'stage__name': 'Initial', 'complete': [True], 'force_complete': [False],
             'id': [task.id]},
            {'stage': second_stage.id, 'stage__name': 'Test pronunciation', 'complete': [False, True],
             'force_complete': [False, False],
             'id': [second_task_2.id, second_task_1.id]}
        ]
        self.assertEqual(len(response.data['info']), 2)
        for i in info_by_case:
            self.assertIn(i, response.data['info'])

        second_task_2 = self.complete_task(second_task_2, {"foo": "boo"})
        self.assertEqual(Task.objects.filter(case=task.case).count(), 4)
        self.assertEqual(Task.objects.filter(case=task.case, stage=second_stage).count(), 2)
        self.assertEqual(Task.objects.filter(case=task.case, stage=final_stage).count(), 1)

    def test_cyclic_chain_RA(self):
        js_schema = {
            "type": "object",
            "properties": {
                'name': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage_schema = {
            "type": "object",
            "properties": {
                'foo': {
                    "type": "string",
                }
            }
        }

        verifier_rank = Rank.objects.create(name="test pronounce")
        RankRecord.objects.create(
            user=self.user,
            rank=verifier_rank)

        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name="Test pronunciation",
                json_schema=json.dumps(second_stage_schema),
                assign_user_by=TaskStageConstants.RANK,
            )
        )
        rank_l = RankLimit.objects.create(
            rank=verifier_rank,
            stage=second_stage,
            open_limit=0,
            total_limit=0,
            is_creation_open=False,
            is_listing_allowed=True,
            is_selection_open=True,
            is_submission_open=True)

        conditional_stage = second_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "=="}]
        ))

        conditional_stage_cyclic = second_stage.add_stage(ConditionalStage(
            conditions=[{"field": "foo", "type": "string", "value": "boo", "condition": "!="}]
        ))

        final_stage_schema = {
            "type": "object",
            "properties": {
                "too": {
                    "type": "string",
                    "title": "what is ur name",
                }
            }
        }

        final_stage = conditional_stage.add_stage(
            TaskStage(
                name='Final stage',
                assign_user_by=TaskStageConstants.STAGE,
                json_schema=json.dumps(final_stage_schema)
            )
        )

        conditional_stage_cyclic.out_stages.add(second_stage)
        conditional_stage_cyclic.save()

        task = self.create_initial_task()
        task = self.complete_task(task, {"name": "Kloop"})

        response_assign = self.get_objects('task-request-assignment', pk=task.out_tasks.get().id)
        self.assertEqual(response_assign.status_code, status.HTTP_200_OK)

        second_task_1 = task.out_tasks.get()
        second_task_1 = self.complete_task(second_task_1, {"foo": "not right"})
        self.assertEqual(Task.objects.filter(case=task.case).count(), 3)
        self.assertEqual(Task.objects.filter(case=task.case, stage=second_stage).count(), 2)

        response_assign = self.get_objects('task-request-assignment', pk=second_task_1.out_tasks.get().id)
        self.assertEqual(response_assign.status_code, status.HTTP_200_OK)

        second_task_2 = second_task_1.out_tasks.get()
        second_task_2 = self.complete_task(second_task_2, {"foo": "boo"})
        self.assertEqual(Task.objects.filter(case=task.case).count(), 4)
        self.assertEqual(Task.objects.filter(case=task.case, stage=second_stage).count(), 2)
        self.assertEqual(Task.objects.filter(case=task.case, stage=final_stage).count(), 1)

    def test_conditional_ping_pong_cyclic_chain(self):
        # first book
        self.initial_stage.json_schema = '{"type":"object","properties":{"foo":{"type":"string"}}}'
        # second creating task
        task_creation_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Creating task using webhook',
                webhook_address='https://us-central1-journal-bb5e3.cloudfunctions.net/random_int_between_0_9',
                webhook_params={"action": "create"}
            )
        )
        # third taks
        completion_stage = task_creation_stage.add_stage(
            TaskStage(
                name='Completion stage',
                json_schema='{"type": "object","properties": {"expression": {"title": "Expression", "type": "string"},"answer": {"type": "integer"}}}',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage,
                copy_input=True
            )
        )
        # fourth ping pong
        conditional_stage = completion_stage.add_stage(
            ConditionalStage(
                name='Conditional ping-pong stage',
                conditions=[{"field": "is_right", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )
        # fifth webhook verification
        verification_webhook_stage = conditional_stage.add_stage(
            TaskStage(
                name='Verification stage using webhook',
                json_schema='{"type":"object","properties":{"is_right":{"type":"string"}}}',
                webhook_address='https://us-central1-journal-bb5e3.cloudfunctions.net/random_int_between_0_9',
                copy_input=True,
                webhook_params={"action": "check"}

            )
        )
        # sixth autocomplete task award
        award_stage = verification_webhook_stage.add_stage(
            TaskStage(
                name='Award stage',
                assign_user_by=TaskStageConstants.AUTO_COMPLETE
            )
        )
        award_stage.add_stage(task_creation_stage)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=completion_stage,
            task_stage_verified=award_stage,
            rank=prize_rank,
            count=5,
            stop_chain=True,
            notification=notification
        )

        init_task = self.create_initial_task()
        init_task = self.complete_task(init_task, {"foo": 'hello world'})
        test_task = init_task.out_tasks.get().out_tasks.get()

        for i in range(task_awards.count):
            expression = test_task.responses['expression'].split(' ')
            sum_of_expression = int(expression[0]) + int(expression[2])
            responses = test_task.responses
            responses['answer'] = sum_of_expression

            test_task = self.complete_task(test_task, responses)
            if i + 1 < task_awards.count:
                test_task = test_task.out_tasks.get().out_tasks.get().out_tasks.get().out_tasks.get()

        self.assertEqual(self.user.ranks.count(), 2)
        self.assertEqual(init_task.case.tasks.filter(stage=completion_stage).count(), 5)
        all_tasks = init_task.case.tasks.all()
        self.assertEqual(all_tasks.count(), 21)
        self.assertEqual(all_tasks[20].stage, award_stage)

    def test_conditional_ping_pong_with_shuffle_sentence_webhook(self):
        # first book
        self.initial_stage.json_schema = '{"type":"object","properties":{"foo":{"type":"string"}}}'
        # second creating task
        task_creation_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Creating task using webhook',
                webhook_address='https://us-central1-journal-bb5e3.cloudfunctions.net/shuffle_sentence',
                webhook_params={"action": "create"}
            )
        )
        # third taks
        completion_stage = task_creation_stage.add_stage(
            TaskStage(
                name='Completion stage',
                json_schema='{"type": "object","properties": {"exercise": {"title": "Put the words in the correct order", "type": "string"},"answer": {"type": "string"}}}',
                assign_user_by=TaskStageConstants.STAGE,
                assign_user_from_stage=self.initial_stage
            )
        )
        CopyField.objects.create(
            copy_by=CopyFieldConstants.CASE,
            task_stage=completion_stage,
            copy_from_stage=task_creation_stage,
            fields_to_copy='exercise->exercise'
        )
        # fourth ping pong
        conditional_stage = completion_stage.add_stage(
            ConditionalStage(
                name='Conditional ping-pong stage',
                conditions=[{"field": "is_right", "type": "string", "value": "no", "condition": "=="}],
                pingpong=True
            )
        )
        # fifth webhook verification
        verification_webhook_stage = conditional_stage.add_stage(
            TaskStage(
                name='Verification stage using webhook',
                json_schema='{"type":"object","properties":{"is_right":{"type":"string"}}}',
                webhook_address='https://us-central1-journal-bb5e3.cloudfunctions.net/shuffle_sentence',
                webhook_params={"action": "check"}

            )
        )
        CopyField.objects.create(
            copy_by=CopyFieldConstants.CASE,
            task_stage=verification_webhook_stage,
            copy_from_stage=task_creation_stage,
            fields_to_copy='sentence->sentence'
        )
        # sixth autocomplete task award
        award_stage = verification_webhook_stage.add_stage(
            TaskStage(
                name='Award stage',
                assign_user_by=TaskStageConstants.AUTO_COMPLETE
            )
        )
        award_stage.add_stage(task_creation_stage)

        prize_rank = Rank.objects.create(name="SUPERMAN")
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=completion_stage,
            task_stage_verified=award_stage,
            rank=prize_rank,
            count=5,
            stop_chain=True,
            notification=notification
        )
        notification_good = Notification.objects.create(
            title="Passed",
            text="Accept",
            campaign=self.campaign
        )
        notification_bad = Notification.objects.create(
            title="Fail",
            text="Remake your task",
            campaign=self.campaign
        )

        auto_notification_1 = AutoNotification.objects.create(
            trigger_stage=verification_webhook_stage,
            recipient_stage=self.initial_stage,
            notification=notification_good,
            go=AutoNotificationConstants.FORWARD
        )
        auto_notification_1 = AutoNotification.objects.create(
            trigger_stage=verification_webhook_stage,
            recipient_stage=self.initial_stage,
            notification=notification_bad,
            go=AutoNotificationConstants.BACKWARD

        )

        init_task = self.create_initial_task()
        init_task = self.complete_task(init_task, {"foo": 'hello world'})
        test_task = init_task.out_tasks.get().out_tasks.get()

        for i in range(task_awards.count):
            responses = test_task.responses
            right_answer = test_task.in_tasks.get().responses['sentence']
            responses['answer'] = right_answer[:-1]

            test_task = self.complete_task(test_task, responses)

            self.assertTrue(test_task.reopened)
            self.assertEqual(test_task.out_tasks.count(), 1)

            responses['answer'] = right_answer
            test_task = self.complete_task(test_task, responses)
            if i + 1 < task_awards.count:
                test_task = test_task.out_tasks.get().out_tasks.get().out_tasks.get().out_tasks.get()

        self.assertEqual(self.user.ranks.count(), 2)
        self.assertEqual(init_task.case.tasks.filter(stage=completion_stage).count(), 5)
        all_tasks = init_task.case.tasks.all()
        self.assertEqual(all_tasks.count(), 21)
        self.assertEqual(all_tasks[20].stage, award_stage)
        self.assertEqual(task_awards.count * 2 + 1, self.user.notifications.count())

    def test_auto_notification_simple(self):
        js_schema = {
            "type": "object",
            "properties": {
                'foo': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Second stage',
                json_schema=self.initial_stage.json_schema,
                assign_user_by=TaskStageConstants.STAGE
            )
        )

        notification = Notification.objects.create(
            title='Congrats you have completed your first task!',
            campaign=self.campaign
        )

        auto_notification = AutoNotification.objects.create(
            trigger_stage=self.initial_stage,
            recipient_stage=self.initial_stage,
            notification=notification
        )

        task = self.create_initial_task()
        task = self.complete_task(task, {"foo": "hello world!"})

        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(self.user.notifications.filter(sender_task=task, receiver_task=task).count(), 1)
        self.assertEqual(self.user.notifications.all()[0].title, notification.title)

    def test_forking_chain_happy(self):
        self.initial_stage.json_schema = {"type": "object",
                                          "properties": {"1": {"enum": ["a", "b", "c", "d"], "type": "string"}}}
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(TaskStage(
            name='You have complete task successfully',
            json_schema=self.initial_stage.json_schema,
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage
        ))
        rating_stage = self.initial_stage.add_stage(TaskStage(
            name='Rating stage',
            json_schema=self.initial_stage.json_schema,
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage
        ))

        task = self.create_initial_task()
        responses = {"1": "a"}
        response = self.complete_task(task, responses=responses, whole_response=True)
        task = Task.objects.get(id=response.data['id'])
        self.assertEqual(task.case.tasks.count(), 3)
        self.assertIn(
            response.data.get('next_direct_id'),
            task.out_tasks.values_list('id', flat=True)
        )

    def test_forking_chain_with_conditional_happy(self):
        self.initial_stage.json_schema = {"type": "object",
                                          "properties": {"1": {"enum": ["a", "b", "c", "d"], "type": "string"}}}
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()

        first_cond_stage = self.initial_stage.add_stage(
            ConditionalStage(
                name='If a',
                conditions=[{"field": "1", "type": "string", "value": "a", "condition": "=="}]
            )
        )

        second_cond_stage = self.initial_stage.add_stage(
            ConditionalStage(
                name='If b',
                conditions=[{"field": "1", "type": "string", "value": "b", "condition": "=="}]
            )
        )

        second_stage = first_cond_stage.add_stage(TaskStage(
            name='You have complete task successfully',
            json_schema=self.initial_stage.json_schema,
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage
        ))

        rating_stage = second_cond_stage.add_stage(TaskStage(
            name='Rating stage',
            json_schema=self.initial_stage.json_schema,
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage
        ))

        task = self.create_initial_task()
        responses = {"1": "a"}
        response = self.complete_task(task, responses=responses, whole_response=True)
        task = Task.objects.get(id=response.data["id"])
        self.assertEqual(task.out_tasks.get().id, response.data['next_direct_id'])

    def test_conditional_and_operator(self):
        task_correct_responses = self.create_initial_task()
        correct_responses = {"1": "a", "2": "a", "3": "a", "4": "a", "5": "a"}
        self.initial_stage.json_schema = {
            "type": "object",
            "properties": {
                "1": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 1", "type": "string"
                },
                "2": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 2", "type": "string"
                },
                "3": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 3", "type": "string"
                },
                "4": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 4", "type": "string"
                },
                "5": {
                    "enum": ["a", "b", "c", "d"], "title": "Question 5", "type": "string"
                }
            },
            "dependencies": {},
            "required": ["1", "2", "3", "4", "5"]
        }
        self.initial_stage.json_schema = json.dumps(self.initial_stage.json_schema)
        self.initial_stage.save()
        task_correct_responses = self.complete_task(
            task_correct_responses,
            responses=correct_responses)
        Quiz.objects.create(
            task_stage=self.initial_stage,
            correct_responses_task=task_correct_responses
        )

        conditional_one = self.initial_stage.add_stage(ConditionalStage(
            name='60 <= x <= 90',
            conditions=[
                {"field": Quiz.SCORE, "type": "integer", "value": "60", "condition": "<="},
                {"field": Quiz.SCORE, "type": "integer", "value": "90", "condition": ">="},
            ]
        ))

        final = conditional_one.add_stage(TaskStage(
            name='Final stage',
            assign_user_by=TaskStageConstants.AUTO_COMPLETE,
            json_schema='{}'
        ))

        notification = Notification.objects.create(
            title='Congrats!',
            campaign=self.campaign
        )
        auto_notification = AutoNotification.objects.create(
            trigger_stage=final,
            recipient_stage=self.initial_stage,
            notification=notification,
            go=AutoNotificationConstants.LAST_ONE
        )

        task = self.create_initial_task()
        responses = {"1": "a", "2": "a", "3": "a", "4": "a", "5": "b"}
        task = self.complete_task(task, responses=responses)

        self.assertEqual(task.case.tasks.count(), 2)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertTrue(self.user.notifications.all()[0].sender_task)
        self.assertEqual(self.user.notifications.all()[0].sender_task.stage, final)
        self.assertEqual(self.user.notifications.all()[0].receiver_task.stage, self.initial_stage)
        self.assertEqual(self.user.notifications.all()[0].trigger_go, auto_notification.go)

    def test_auto_notification_last_one_option_as_go(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "foo": {"type": "string"}
            }
        })
        notification = Notification.objects.create(
            title='Congrats!',
            campaign=self.campaign
        )
        AutoNotification.objects.create(
            trigger_stage=self.initial_stage,
            recipient_stage=self.initial_stage,
            notification=notification,
            go=AutoNotificationConstants.LAST_ONE
        )
        task = self.create_initial_task()
        task = self.complete_task(task, {"foo": "boo"})
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(self.user.notifications.filter(sender_task=task,
                                                        receiver_task=task).count(), 1)
        response = self.get_objects('task-user-selectable', client=self.employee_client)

    def test_number_rank_endpoint(self):
        CampaignManagement.objects.create(user=self.employee,
                                          campaign=self.campaign)
        manager = CustomUser.objects.create_user(username="manager",
                                                       email='manager@email.com',
                                                       password='manager')
        track = Track.objects.create(campaign=self.campaign)
        rank1 = Rank.objects.create(name='rank1', track=track)
        rank2 = Rank.objects.create(name='rank2', track=track)
        rank2.prerequisite_ranks.add(rank1)
        rank3 = Rank.objects.create(name='rank3', track=track)
        track.default_rank = rank1
        self.campaign.default_track = track
        self.campaign.save(), track.save()

        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=self.initial_stage,
            rank=rank3,
            count=1,
        )

        RankRecord.objects.create(user=self.employee,
                                  rank=rank1)
        RankRecord.objects.create(user=manager,
                                  rank=rank1)
        RankRecord.objects.create(user=self.employee,
                                  rank=rank2)
        RankRecord.objects.create(user=self.employee,
                                  rank=rank3)

        response = self.get_objects('numberrank-list', client=self.employee_client)
        data = response.json()[0]

        expected_count_rank = 4

        default_rank = data['ranks'][0]
        rank1 = data['ranks'][1]
        rank2 = data['ranks'][2]
        rank3 = data['ranks'][3]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(data['ranks']), expected_count_rank)
        self.assertEqual(default_rank['count'], 0)
        self.assertEqual(rank1['count'], 2)
        self.assertEqual(rank2['count'], 1)
        self.assertEqual(rank3['count'], 1)
        self.assertEqual(rank1['condition'], 'default')
        self.assertEqual(rank2['condition'], 'prerequisite_ranks')
        self.assertEqual(rank3['condition'], 'task_awards')

    def test_assign_rank_by_parent_rank(self):
        schema = {"type": "object", "properties": {"foo": {"type": "string", "title": "what is ur name"}}}
        self.initial_stage.json_schema = json.dumps(schema)
        prize_rank_1 = Rank.objects.create(name='GOOD RANK')
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        task_awards = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=self.initial_stage,
            rank=prize_rank_1,
            count=1,
            notification=notification
        )

        second_stage = self.initial_stage.add_stage(TaskStage(
            name='Second stage',
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage,
            json_schema=self.initial_stage.json_schema
        ))
        prize_rank_2 = Rank.objects.create(name='BEST RANK')
        task_awards = TaskAward.objects.create(
            task_stage_completion=second_stage,
            task_stage_verified=second_stage,
            rank=prize_rank_2,
            count=1,
            notification=notification
        )

        super_rank = Rank.objects.create(name='SUPERMAN RANK')
        super_rank.prerequisite_ranks.add(prize_rank_1)
        super_rank.prerequisite_ranks.add(prize_rank_2)
        super_rank.save()
        resp = {"foo": "hello world"}
        task = self.create_initial_task()
        task = self.complete_task(task, resp)
        second_task = task.out_tasks.get()
        second_task = self.complete_task(second_task, resp)

        self.assertEqual(Notification.objects.count(), 3)
        self.assertEqual(self.user.ranks.count(), 4)

    def test_assignee_new_ranks_based_on_prerequisite(self):
        prize_rank_1 = Rank.objects.create(name='Good', track=self.user.ranks.all()[0].track)
        prize_rank_2 = Rank.objects.create(name='Best', track=self.user.ranks.all()[0].track)
        prize_rank_3 = Rank.objects.create(name='Superman', track=self.user.ranks.all()[0].track)
        prize_rank_3.prerequisite_ranks.add(prize_rank_1)
        prize_rank_3.prerequisite_ranks.add(prize_rank_2)
        notification = Notification.objects.create(
            title="You achieve new rank",
            text="Congratulations! You achieve new rank!",
            campaign=self.campaign
        )
        schema = {"type": "object", "properties": {"foo": {"type": "string", "title": "what is ur name"}}}

        self.initial_stage.json_schema = json.dumps(schema)
        self.initial_stage.save()
        task_award_1 = TaskAward.objects.create(
            task_stage_completion=self.initial_stage,
            task_stage_verified=self.initial_stage,
            rank=prize_rank_1,
            count=5,
            notification=notification
        )

        another_chain = Chain.objects.create(name='Chain for getting best', campaign=self.campaign)
        new_initial = TaskStage.objects.create(
            name="Initial for Good persons",
            x_pos=1,
            y_pos=1,
            json_schema=self.initial_stage.json_schema,
            chain=another_chain,
            is_creatable=True)
        rank_limit = RankLimit.objects.create(
            rank=prize_rank_1,
            stage=new_initial,
            open_limit=0,
            total_limit=0,
            is_listing_allowed=True,
            is_creation_open=True
        )
        task_award_2 = TaskAward.objects.create(
            task_stage_completion=new_initial,
            task_stage_verified=new_initial,
            rank=prize_rank_2,
            count=5,
            notification=notification
        )

        responses = {"foo": "Kloop"}
        task = self.create_initial_task()
        for i in range(task_award_1.count):
            task = self.complete_task(task, responses)
            if task_award_1.count - 1 > i:
                task = self.create_initial_task()
                self.assertNotIn(prize_rank_2, self.user.ranks.all())
                self.assertNotIn(prize_rank_3, self.user.ranks.all())
            else:
                self.assertIn(prize_rank_1, self.user.ranks.all())
        self.assertIn(prize_rank_1, self.user.ranks.all())
        self.assertNotIn(prize_rank_2, self.user.ranks.all())
        self.assertNotIn(prize_rank_3, self.user.ranks.all())
        another_rank_1 = Rank.objects.create(name='Barmaley', track=self.user.ranks.all()[0].track)
        another_rank_2 = Rank.objects.create(name='Jeenbekov', track=self.user.ranks.all()[0].track)
        self.user.ranks.add(another_rank_2)
        self.user.ranks.add(another_rank_1)
        self.user.ranks.add(prize_rank_1)

        task = self.create_task(new_initial)
        for i in range(task_award_2.count):
            task = self.complete_task(task, responses)
            if task_award_2.count - 1 > i:
                task = self.create_task(new_initial)
                self.assertIn(prize_rank_1, self.user.ranks.all())
                self.assertNotIn(prize_rank_2, self.user.ranks.all())
                self.assertNotIn(prize_rank_3, self.user.ranks.all())
            else:
                self.assertIn(prize_rank_2, self.user.ranks.all())
                self.assertIn(prize_rank_3, self.user.ranks.all())
        self.assertIn(prize_rank_1, self.user.ranks.all())
        self.assertIn(prize_rank_2, self.user.ranks.all())
        self.assertIn(prize_rank_3, self.user.ranks.all())

    def test_error_creating_for_managers(self):
        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {
                    "title": "Question 1",
                    "type": "string"
                }
            },
            "required": [
                "answer"
            ]
        })
        second_stage = self.initial_stage.add_stage(
            TaskStage(
                name="Stage with webhook",
                json_schema=self.initial_stage.json_schema,
            )
        )
        Webhook.objects.create(
            task_stage=second_stage,
            url="https://us-central1-journal-bb5e3.cloudfunctions.net/exercise_translate_word",
            is_triggered=True,
        )
        task = self.create_initial_task()
        task = self.complete_task(task, {"answer": "hello world"})
        self.assertEqual(ErrorGroup.objects.count(), 1)
        self.assertEqual(ErrorItem.objects.count(), 1)

        task = self.create_initial_task()
        task = self.complete_task(task, {"answer": "hello world"})
        self.assertEqual(ErrorGroup.objects.count(), 1)
        self.assertEqual(ErrorItem.objects.count(), 2)

        err_campaigns = Campaign.objects.filter(name=ErrorConstants.ERROR_CAMPAIGN)
        self.assertEqual(err_campaigns.count(), 1)
        self.assertEqual(err_campaigns[0].chains.count(), 1)
        err_tasks = Task.objects.filter(stage__chain__campaign=err_campaigns[0])
        self.assertEqual(err_tasks.count(), 2)

    def test_last_task_notification_errors_creation(self):
        js_schema = {
            "type": "object",
            "properties": {
                'answer': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        rank_verifier = Rank.objects.create(name='verifier rank')
        RankRecord.objects.create(rank=rank_verifier, user=self.employee)

        second_stage = self.initial_stage.add_stage(TaskStage(
            name="Get on verification",
            assign_user_by=TaskStageConstants.RANK,
            json_schema=json.dumps(js_schema)
        ))
        RankLimit.objects.create(rank=rank_verifier, stage=second_stage)
        third_stage = second_stage.add_stage(TaskStage(
            name="Some routine stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=second_stage,
            json_schema=json.dumps(js_schema)
        ))
        four_stage = third_stage.add_stage(TaskStage(
            name="Finish stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=third_stage,
            json_schema=json.dumps(js_schema)
        ))

        notif_1 = Notification.objects.create(
            title='It is your first step along the path to the goal.',
            text='',
            campaign=self.campaign,
        )
        notif_2 = Notification.objects.create(
            title='Verifier get your task and complete it already.',
            text='You almost finish your chan',
            campaign=self.campaign,
        )
        notif_3 = Notification.objects.create(
            title='Documents in the process',
            text='',
            campaign=self.campaign,
        )
        notif_4 = Notification.objects.create(
            title='You have finished your chain!',
            text='',
            campaign=self.campaign,
        )

        AutoNotification.objects.create(
            trigger_stage=self.initial_stage,
            recipient_stage=self.initial_stage,
            notification=notif_1,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            trigger_stage=second_stage,
            recipient_stage=self.initial_stage,
            notification=notif_2,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            trigger_stage=self.initial_stage,
            recipient_stage=third_stage,
            notification=notif_3,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            recipient_stage=four_stage,
            trigger_stage=self.initial_stage,
            notification=notif_4,
            go=AutoNotificationConstants.LAST_ONE,
        )

        task = self.create_initial_task()
        task = self.complete_task(
            task, {"answer": "Hello World!My name is Artur"}
        )

        self.assertEqual(ErrorItem.objects.count(), 1)
        self.assertEqual(ErrorItem.objects.get().campaign, self.campaign)

    def test_last_task_notification(self):
        js_schema = {
            "type": "object",
            "properties": {
                'answer': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(TaskStage(
            name="Get on verification",
            assign_user_by=TaskStageConstants.RANK,
            json_schema=json.dumps(js_schema)
        ))
        third_stage = second_stage.add_stage(TaskStage(
            name="Some routine stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=second_stage,
            json_schema=json.dumps(js_schema)
        ))
        four_stage = third_stage.add_stage(TaskStage(
            name="Finish stage",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=third_stage,
            json_schema=json.dumps(js_schema)
        ))

        notif_1 = Notification.objects.create(
            title='It is your first step along the path to the goal.',
            text='',
            campaign=self.campaign,
        )
        notif_2 = Notification.objects.create(
            title='Verifier get your task and complete it already.',
            text='You almost finish your chan',
            campaign=self.campaign,
        )
        notif_3 = Notification.objects.create(
            title='Documents in the process',
            text='',
            campaign=self.campaign,
        )
        notif_4 = Notification.objects.create(
            title='You have finished your chain!',
            text='',
            campaign=self.campaign,
        )

        AutoNotification.objects.create(
            trigger_stage=self.initial_stage,
            recipient_stage=self.initial_stage,
            notification=notif_1,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            trigger_stage=second_stage,
            recipient_stage=self.initial_stage,
            notification=notif_2,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            trigger_stage=third_stage,
            recipient_stage=self.initial_stage,
            notification=notif_3,
            go=AutoNotificationConstants.FORWARD,
        )
        AutoNotification.objects.create(
            trigger_stage=four_stage,
            recipient_stage=self.initial_stage,
            notification=notif_4,
            go=AutoNotificationConstants.LAST_ONE,
        )

        verifier = self.prepare_client(second_stage, self.employee)

        task = self.create_initial_task()
        task = self.complete_task(
            task, {"answer": "Hello World!My name is Artur"}
        )
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(Notification.objects.count(), 5)

        response = self.get_objects('notification-last-task-notifications')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'],
                         self.user.notifications.get().id)

        out_task = self.request_assignment(
            task.out_tasks.get(), verifier
        )

        step = 1
        total_notifications_count = 5
        for i, notification in enumerate([notif_2, notif_3, notif_4]):
            out_task = self.complete_task(
                out_task,
                {"answer": f"Good answer. Process {step}/4"},
                client=verifier
            )
            total_notifications_count += 1
            step += 1
            # check notification creation on task completion
            self.assertTrue(Task.objects.get(pk=out_task.pk).responses)
            self.assertEqual(self.user.notifications.count(), step)
            self.assertEqual(Notification.objects.count(),
                             total_notifications_count)

            # check last notifications for every tasks
            response = self.get_objects('notification-last-task-notifications')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['count'], 1)
            notification_received = response.data['results'][0]
            self.assertEqual(notification_received['id'],
                             self.user.notifications
                             .order_by('-created_at')[0].id)
            self.assertEqual(notification_received['title'], notification.title)
            if step < 4:
                out_task = out_task.out_tasks.get()

    def test_trigger_webhook_endpoint(self):
        js_schema = {
            "type": "object",
            "properties": {
                'answer': {
                    "type": "string",
                }
            }
        }
        self.initial_stage.json_schema = json.dumps(js_schema)
        self.initial_stage.save()

        second_stage = self.initial_stage.add_stage(TaskStage(
            name="Get on verification",
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage,
            json_schema=json.dumps(js_schema)
        ))
        Webhook.objects.create(
            task_stage=self.initial_stage,
            url='https://us-central1-journal-bb5e3.cloudfunctions.net/echo_function',
            is_triggered=False,
            which_responses=WebhookConstants.CURRENT_TASK_RESPONSES,
        )
        Webhook.objects.create(
            task_stage=second_stage,
            url='https://us-central1-journal-bb5e3.cloudfunctions.net/echo_function',
            is_triggered=False,
            which_responses=WebhookConstants.IN_RESPONSES,
        )

        task = self.create_initial_task()
        task = self.update_task_responses(task, {"answer": "Hello world!"})

        response = self.get_objects('task-trigger-webhook',  pk=task.pk)
        echo_response = {'echo': {'answer': 'Hello world!'},
                         'answer': 'Hello world!', 'status': 200}
        task = Task.objects.get(id=task.id)
        task = self.complete_task(task, task.responses)
        self.assertEqual(task.responses, echo_response)

        next_task = task.out_tasks.get()
        response = self.get_objects('task-trigger-webhook',  pk=next_task.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({'echo': [echo_response], 'status': 200},
                         Task.objects.get(id=next_task.id).responses)

    def test_campaign_linker(self):
        pepsi_data = self.generate_new_basic_campaign("Pepsi")
        fanta_data = self.generate_new_basic_campaign("Fanta")
        sprite_data = self.generate_new_basic_campaign("Sprite")

        self.assertEqual(Rank.objects.count(), 5)
        self.assertEqual(Track.objects.count(), 4)
        self.assertEqual(Campaign.objects.count(), 4)

        # creation queries to give another campaign ranks
        cola_to_pepsi = CampaignLinker.objects.create(
            name="From cola to PEPSI",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=pepsi_data["campaign"]
        )
        cola_to_fanta = CampaignLinker.objects.create(
            name="From cola to FANTA",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=fanta_data["campaign"]
        )
        cola_to_sprite = CampaignLinker.objects.create(
            name="From cola to SPRITE",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=sprite_data["campaign"]
        )

        # Prize Notification
        pepsi_not = Notification.objects.create(
            title="You access new rank from Pepsi campaign!",
            campaign=pepsi_data["campaign"]
        )
        sprite_not = Notification.objects.create(
            title="You access new rank from Pepsi campaign!",
            campaign=pepsi_data["campaign"]
        )
        pepsi_auto_not = AutoNotification.objects.create(
            notification=pepsi_not,
            go=AutoNotificationConstants.FORWARD
        )
        sprite_auto_not = AutoNotification.objects.create(
            notification=pepsi_not,
            go=AutoNotificationConstants.FORWARD
        )
        # approving links
        ApproveLink.objects.create(
            campaign=pepsi_data['campaign'],
            linker=cola_to_pepsi,
            rank=pepsi_data['rank'],
            notification=pepsi_auto_not,
            approved=True
        )
        ApproveLink.objects.create(
            campaign=sprite_data['campaign'],
            linker=cola_to_sprite,
            rank=sprite_data['rank'],
            notification=sprite_auto_not
        )

        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        task = self.create_initial_task()
        task = self.complete_task(task, {"answer": "Hello!"})
        self.assertTrue(task.complete)

        self.assertEqual(self.user.ranks.count(), 2)
        self.assertIn(pepsi_data['rank'], self.user.ranks.all())
        self.assertEqual(Notification.objects.count(), 3)
        self.assertEqual(self.user.notifications.count(), 1)

    def test_campaign_linker_assignee_rank(self):
        pepsi_data = self.generate_new_basic_campaign("Pepsi")
        fanta_data = self.generate_new_basic_campaign("Fanta")
        sprite_data = self.generate_new_basic_campaign("Sprite")

        self.assertEqual(Rank.objects.count(), 5)
        self.assertEqual(Track.objects.count(), 4)
        self.assertEqual(Campaign.objects.count(), 4)

        # creation queries to give another campaign ranks
        cola_to_pepsi = CampaignLinker.objects.create(
            name="From cola to PEPSI",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=pepsi_data["campaign"]
        )
        cola_to_fanta = CampaignLinker.objects.create(
            name="From cola to FANTA",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=fanta_data["campaign"]
        )
        cola_to_sprite = CampaignLinker.objects.create(
            name="From cola to SPRITE",
            out_stage=self.initial_stage,
            stage_with_user=self.initial_stage,
            target=sprite_data["campaign"]
        )

        # Prize Notification
        pepsi_not = Notification.objects.create(
            title="You access new rank from Pepsi campaign!",
            campaign=pepsi_data["campaign"]
        )
        sprite_not = Notification.objects.create(
            title="You access new rank from Pepsi campaign!",
            campaign=pepsi_data["campaign"]
        )
        pepsi_auto_not = AutoNotification.objects.create(
            notification=pepsi_not,
            go=AutoNotificationConstants.FORWARD
        )
        sprite_auto_not = AutoNotification.objects.create(
            notification=pepsi_not,
            go=AutoNotificationConstants.FORWARD
        )
        # approving links
        pepsi_init_stage = TaskStage.objects.create(
            name="Initial pepsi stage",
            x_pos=1,
            y_pos=1,
            chain=pepsi_data['chain'],
            is_creatable=True)
        ApproveLink.objects.create(
            campaign=pepsi_data['campaign'],
            linker=cola_to_pepsi,
            rank=pepsi_data['rank'],
            task_stage=pepsi_init_stage,
            notification=pepsi_auto_not,
            approved=True
        )

        self.initial_stage.json_schema = json.dumps({
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        })
        task = self.create_initial_task()
        response = self.complete_task(task, {"answer": "Hello!"}, whole_response=True)
        response_content = json.loads(response.content)
        task = Task.objects.get(id=response_content['id'])

        self.assertTrue(response_content['is_new_campaign'])
        self.assertTrue(task.complete)
        self.assertEqual(self.user.tasks.count(), 2)

        self.assertIn(pepsi_data['rank'], self.user.ranks.all())
        self.assertNotIn(sprite_data['rank'], self.user.ranks.all())

        self.assertEqual(Notification.objects.count(), 3)
        self.assertEqual(self.user.notifications.count(), 1)

    def test_return_task_after_conditional(self):
        self.initial_stage.json_schema = json.dumps(
            {"type": "object", "properties": {"answer": {"type": "string"}}}
        )
        self.initial_stage.save()
        # fourth ping pong
        conditional_stage = self.initial_stage.add_stage(
            ConditionalStage(
                name='Conditional ping-pong stage',
                conditions=[
                    {"field": "answer", "type": "string", "value": "pass",
                     "condition": "=="}],
            )
        )

        final = conditional_stage.add_stage(TaskStage(
            name='Final stage',
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage,
            json_schema='{}'
        ))

        task = self.create_initial_task()
        response = self.complete_task(
            task,
            {"answer": "nopass"},
            whole_response=True
        )
        self.assertEqual(json.loads(response.content),
                         {"message": "Task saved.", "id": task.id})
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(self.user.tasks.filter(case=task.case).count(), 1)
        self.assertEqual(self.user.tasks.count(), 1)

        task = self.create_initial_task()
        response = self.complete_task(
            task,
            {"answer": "pass"},
            whole_response=True
        )
        self.assertEqual(json.loads(response.content),
                         {"message": "Next direct task is available.",
                          "id": task.id,
                          "is_new_campaign": False,
                          "next_direct_id": task.out_tasks.get().id})
        self.assertEqual(Task.objects.count(), 3)
        self.assertEqual(self.user.tasks.filter(case=task.case).count(), 2)
        self.assertEqual(self.user.tasks.count(), 3)

    def test_get_next_task_after_autocomplete_stage(self):
        self.initial_stage.json_schema = json.dumps(
            {"type": "object", "properties": {"answer": {"type": "string"}}}
        )
        self.initial_stage.save()
        # fourth ping pong
        autocomplete_stage = self.initial_stage.add_stage(
            TaskStage(
                name='Autocomplete',
                assign_user_by=TaskStageConstants.AUTO_COMPLETE
            )
        )

        final = autocomplete_stage.add_stage(TaskStage(
            name='Final stage',
            assign_user_by=TaskStageConstants.STAGE,
            assign_user_from_stage=self.initial_stage,
            json_schema='{}'
        ))

        task = self.create_initial_task()
        response = self.complete_task(
            task,
            {"answer": "nopass"},
            whole_response=True
        )
        self.assertEqual(json.loads(response.content),
                         {"message": "Next direct task is available.",
                          "id": task.id,
                          "is_new_campaign": False,
                          "next_direct_id": task.id+2})

    def test_campaign_list_user_campaigns(self):
        # check that employee doesn't have any rank
        response = self.get_objects(
            "campaign-list-user-campaigns", client=self.employee_client
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(to_json(response.content)['count'], 0)

        # join employee to campaign
        self.campaign.open = True
        self.campaign.save()
        response = self.employee_client.get(
            reverse("campaign-join-campaign", kwargs={"pk": self.campaign.id})
        )
        self.assertEqual(response.status_code, 200)

        # check that employee joined
        response = self.get_objects(
            "campaign-list-user-campaigns", client=self.employee_client
        )
        response_content = to_json(response.content)
        self.assertEqual(response_content["count"],1)
        self.assertEqual(
            response_content["results"][0]["notifications_count"], 0)

        # check serializer works properly
        notifications_count = 15
        [Notification.objects.create(
            title="Hello world",
            campaign=self.campaign
        ) for _ in range(notifications_count)]
        response = self.get_objects(
            "campaign-list-user-campaigns", client=self.employee_client
        )
        response_content = to_json(response.content)
        self.assertEqual(response_content["count"], 1)
        self.assertEqual(
            response_content["results"][0]["notifications_count"], 0)

        # check serializer works properly
        notifications_count = int(notifications_count/2)
        [Notification.objects.all().first().delete()
         for _ in range(notifications_count+1)]
        response = self.get_objects(
            "campaign-list-user-campaigns", client=self.employee_client
        )
        response_content = to_json(response.content)
        self.assertEqual(response_content["count"], 1)
        self.assertEqual(
            response_content["results"][0]["notifications_count"],
            0)
    def test_task_own_schema(self):
        stage_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        }
        stage_ui_schema = {"ui:order": ["answer"]}
        task_schema = {
            "type": "object",
            "properties": {
                "answer_to_generated_question": {"type": "string"}
            },
            "required": ["answer"]
        }
        task_ui_schema = {"ui:order": ["answer_to_generated_question"]}

        self.initial_stage.schema_source = TaskStageSchemaSourceConstants.TASK

        self.initial_stage.json_schema = json.dumps(stage_schema)
        self.initial_stage.ui_schema = json.dumps(stage_ui_schema)
        self.initial_stage.save()

        task = self.create_initial_task()
        task.schema = json.dumps(task_schema)
        task.ui_schema = json.dumps(task_ui_schema)
        task.save()

        response = self.get_objects("task-detail", pk=task.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["stage"]["json_schema"],
                         json.dumps(task_schema))
        self.assertEqual(response.data["stage"]["ui_schema"],
                         json.dumps(task_ui_schema))

    def test_task_stage_schema(self):
        stage_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            },
            "required": ["answer"]
        }
        stage_ui_schema = {"ui:order": ["answer"]}
        task_schema = {
            "type": "object",
            "properties": {
                "answer_to_generated_question": {"type": "string"}
            },
            "required": ["answer"]
        }
        task_ui_schema = {"ui:order": ["answer_to_generated_question"]}

        self.initial_stage.json_schema = json.dumps(stage_schema)
        self.initial_stage.ui_schema = json.dumps(stage_ui_schema)
        self.initial_stage.save()

        task = self.create_initial_task()
        task.schema = json.dumps(task_schema)
        task.ui_schema = json.dumps(task_ui_schema)
        task.save()

        response = self.get_objects("task-detail", pk=task.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["stage"]["json_schema"],
                         json.dumps(stage_schema))
        self.assertEqual(response.data["stage"]["ui_schema"],
                         json.dumps(stage_ui_schema))
