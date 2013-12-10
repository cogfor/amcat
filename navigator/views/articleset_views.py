###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Affero General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Affero General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

from django.core.urlresolvers import reverse

from amcat.scripts.actions.sample_articleset import SampleSet
from amcat.scripts.actions.import_articleset import ImportSet
from navigator.views.scriptview import ProjectScriptView
from navigator.views.projectview import ProjectViewMixin, HierarchicalViewMixin, BreadCrumbMixin
from navigator.views.datatableview import DatatableMixin
from amcat.models import Project, ArticleSet
from api.rest.resources import SearchResource
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from django.views.generic.base import RedirectView

class SampleSetView(ProjectScriptView):
    script = SampleSet

    def get_success_url(self):
        return reverse("project-articlesets", kwargs=dict(id=self.project.id))
    
class ImportSetView(ProjectScriptView):
    script = ImportSet

    
    def get_success_url(self):
        target = self.form.cleaned_data["target_project"]
        return reverse("project-articlesets", kwargs=dict(id=target.id))
    
    def get_form(self, form_class):
        form = super(ImportSetView, self).get_form(form_class)
        if self.request.method == 'GET':
            # list current users favourite projects but exclude already imported and currect project
            qs = Project.objects.filter(favourite_users=self.request.user.get_profile())
            qs = qs.exclude(articlesets=self.url_data["articleset"])
            qs = qs.exclude(pk=self.project.id)
            form.fields['target_project'].queryset = qs
            form.fields['target_project'].help_text = "Only showing your favourite projects that do not use this set already"

        return form

from api.rest.datatable import FavouriteDatatable
    
class ArticleSetListView(HierarchicalViewMixin,ProjectViewMixin, BreadCrumbMixin, DatatableMixin, ListView):
    model = ArticleSet
    parent = None
    base_url = "projects/(?P<project_id>[0-9]+)"
    context_category = 'Articles'
    
    resource = ArticleSet
    rowlink = './{id}'

    @classmethod
    def get_url_patterns(cls):
        patterns = list(super(ArticleSetListView, cls).get_url_patterns())
        #patterns.append(patterns[0][:-1] + "(?P<what>/[a-z]+)?")
        return patterns

        
    def get_datatable(self):
        """Create the Datatable object"""
        url = reverse('article set-details', args=[self.project.id, 123]) 
        table = FavouriteDatatable(resource=self.get_resource(), label="article set",
                                   set_url=url + "?star=1", unset_url=url+"?star=0")
        table = table.rowlink_reverse('article set-details', args=[self.project.id, '{id}'])
        table = table.hide("project")
        table = self.filter_table(table)
        return table


    
class ArticleSetDetailsView(HierarchicalViewMixin, ProjectViewMixin, BreadCrumbMixin, DatatableMixin, DetailView):
    parent = ArticleSetListView
    model = ArticleSet
    context_category = 'Articles'
        
    resource = SearchResource
    rowlink = './{id}'
    
    def filter_table(self, table):
        return table.filter(sets=self.object.id)

    def get_context_data(self, **kwargs):
        context = super(ArticleSetDetailsView, self).get_context_data(**kwargs)

        star = self.request.GET.get("star")
        starred = self.project.favourite_articlesets.filter(pk=self.object.id).exists()
        if (star is not None):
            if bool(int(star)) != starred:
                starred = not starred
                if starred:
                    self.project.favourite_articlesets.add(self.object.id)
                else:
                    self.project.favourite_articlesets.remove(self.object.id)
        context['starred'] = starred
        return context

class RefreshArticleSetView(RedirectView):
    def get_redirect_url(self, projectid, pk):
        # refresh the queryset. Probably not the nicest way to do this (?)
        ArticleSet.objects.get(pk=pk).refresh_index(full_refresh=True)
        return reverse("articleset", args=[projectid, pk])
