from django.db.models import Count
from django_q.tasks import async_task, result
from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from api.models import Campaign, Chain, TaskStage, \
    WebHookStage, ConditionalStage, Case, Task, Rank, \
    RankLimit, Track, RankRecord
from api.serializer import CampaignSerializer, ChainSerializer, \
    TaskStageSerializer, WebHookStageSerializer, ConditionalStageSerializer, \
    CaseSerializer, RankSerializer, RankLimitSerializer, \
    TrackSerializer, RankRecordSerializer, TaskCreateSerializer, TaskEditSerializer, \
    TaskDefaultSerializer, TaskRequestAssignmentSerializer
from api.asyncstuff import process_completed_task
from api.permissions import CampaignAccessPolicy


class CampaignViewSet(viewsets.ModelViewSet):

    serializer_class = CampaignSerializer
    queryset = Campaign.objects.all()

    # permission_classes = (CampaignAccessPolicy,)


class ChainViewSet(viewsets.ModelViewSet):
    filterset_fields = ['campaign', ]
    serializer_class = ChainSerializer
    queryset = Chain.objects.all()


class TaskStageViewSet(viewsets.ModelViewSet):
    # filterset_fields = ['chain', 'chain__campaign', 'is_creatable', 'ranks',
    #                     'ranks__users', 'ranklimits__open_limit',
    #                     'ranklimits__total_limit',
    #                     'ranklimits__is_creation_open']
    filterset_fields = {
        'chain': ['exact'],
        'chain__campaign': ['exact'],
        'is_creatable': ['exact'],
        'ranks': ['exact'],
        'ranks__users': ['exact'],
        'ranklimits__is_creation_open': ['exact'],
        'ranklimits__total_limit': ['exact', 'lt', 'gt'],
        'ranklimits__open_limit': ['exact', 'lt', 'gt']
    }
    queryset = TaskStage.objects.all()
    serializer_class = TaskStageSerializer

    @action(detail=False)
    def user_relevant(self, request):
        stages = self.filter_queryset(self.get_queryset())\
            .filter(is_creatable=True)\
            .filter(ranks__users=request.user.id)\
            .filter(ranklimits__is_creation_open=True)\
            .distinct()
        filtered_stages = TaskStage.objects.none()
        for stage in stages:
            tasks = Task.objects.filter(assignee=request.user.id)\
                .filter(stage=stage).distinct()
            total = len(tasks)
            print(total)
            incomplete = len(tasks.filter(complete=False))
            print(incomplete)
            ranklimits = RankLimit.objects.filter(stage=stage) \
                .filter(rank__rankrecord__user__id=request.user.id)
            for ranklimit in ranklimits:
                print(ranklimit.total_limit)
                print(ranklimit.open_limit)
                if ((ranklimit.open_limit > incomplete and ranklimit.total_limit > total) or
                        (ranklimit.open_limit == 0 and ranklimit.total_limit == total) or
                        (ranklimit.open_limit > incomplete and ranklimit.total_limit == total) or
                        (ranklimit.open_limit == 0 and ranklimit.total_limit > total)
                ):
                    filtered_stages |= TaskStage.objects.filter(pk=stage.pk)

        # tasks_count = tasks.values('stage', 'complete')\
        #     .annotate(count=Count('id'))
        # print(tasks_count)
        serializer = self.get_serializer(filtered_stages.distinct(), many=True)
        return Response(serializer.data)


class WebHookStageViewSet(viewsets.ModelViewSet):
    filterset_fields = ['chain', ]
    queryset = WebHookStage.objects.all()
    serializer_class = WebHookStageSerializer


class ConditionalStageViewSet(viewsets.ModelViewSet):
    filterset_fields = ['chain', ]
    queryset = ConditionalStage.objects.all()
    serializer_class = ConditionalStageSerializer


class CaseViewSet(viewsets.ModelViewSet):
    queryset = Case.objects.all()
    serializer_class = CaseSerializer


class TaskViewSet(viewsets.ModelViewSet):
    filterset_fields = ['stage',
                        'case',
                        'stage__chain__campaign',
                        'assignee',
                        'complete']
    queryset = Task.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        elif self.action == 'update' or self.action == 'partial_update':
            return TaskEditSerializer
        elif self.action == 'request_assignment':
            return TaskRequestAssignmentSerializer
        else:
            return TaskDefaultSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            case = Case.objects.create()
            serializer.save(case=case)
            data = serializer.data
            if data['complete']:
                process_completed_task(self.get_object())
            # if data['complete']:
            #     result(async_task(process_completed_task,
            #                       data['id'],
            #                       task_name='process_completed_task',
            #                       group='follow_chain'))
            return Response(data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance,
                                         data=request.data,
                                         partial=partial)
        if serializer.is_valid():
            serializer.save()
            if getattr(instance, '_prefetched_objects_cache', None):
                # If 'prefetch_related' has been applied to a queryset, we need to
                # forcibly invalidate the prefetch cache on the instance.
                instance._prefetched_objects_cache = {}
            data = serializer.data
            data['id'] = instance.id
            if data['complete']:
                process_completed_task(instance)
            # if data['complete']:
            #     result(async_task(process_completed_task,
            #                data['id'],
            #                task_name='process_completed_task',
            #                group='follow_chain'))
            return Response(data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @action(detail=False)
    def user_relevant(self, request):
        tasks = self.filter_queryset(self.get_queryset()) \
            .filter(assignee=request.user)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def user_selectable(self, request):
        tasks = self.filter_queryset(self.get_queryset()) \
            .filter(complete=False) \
            .filter(assignee__isnull=True) \
            .filter(stage__ranks__users=request.user.id) \
            .filter(stage__ranklimits__is_selection_open=True) \
            .filter(stage__ranklimits__is_listing_allowed=True) \
            .distinct()
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post', 'get'])
    def request_assignment(self, request, pk=None): # TODO: Add permissions to block changing assignee
        task = self.get_object()
        serializer = self.get_serializer(task, request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'status': 'assignment granted', 'id': task.id})
        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post', 'get'])
    def release_assignment(self, request, pk=None):  # TODO: Add permissions to block changing assignee
        task = self.get_object()
        task.assignee = None
        task.save()
        return Response({'status': 'assignment released'})


class RankViewSet(viewsets.ModelViewSet):
    queryset = Rank.objects.all()
    serializer_class = RankSerializer


class RankRecordViewSet(viewsets.ModelViewSet):
    queryset = RankRecord.objects.all()
    serializer_class = RankRecordSerializer


class RankLimitViewSet(viewsets.ModelViewSet):
    filterset_fields = ['rank', ]
    queryset = RankLimit.objects.all()
    serializer_class = RankLimitSerializer


class TrackViewSet(viewsets.ModelViewSet):
    queryset = Track.objects.all()
    serializer_class = TrackSerializer
