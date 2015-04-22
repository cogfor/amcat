##########################################################################
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
from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.template import Context
from django.template.loader import get_template
from amcat.models import ArticleSet
from amcat.models import Project
from amcat.models import Role
from amcat.models.authorisation import ROLE_PROJECT_WRITER

from amcat.scripts.query import QueryAction, QueryActionForm
from amcat.tools.keywordsearch import SelectionSearch


OK_TEMPLATE = get_template("query/ok.html")


class SaveAsSetForm(QueryActionForm):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), empty_label=None)
    name = forms.CharField(required=True)
    #provenance = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super(SaveAsSetForm, self).__init__(*args, **kwargs)
        rw_role = Role.objects.get(id=ROLE_PROJECT_WRITER)
        self.fields["project"].queryset = self.user.userprofile.get_projects(rw_role)
        self.fields["project"].initial = self.project

    def clean_name(self):
        new_name = self.cleaned_data["name"]
        project = self.cleaned_data["project"]

        all_articlesets = project.articlesets_set.all()
        if all_articlesets.filter(name__iexact=new_name).exists():
            error_msg = "An articleset called {0!r} already exists in project {1.name!r}."
            raise ValidationError(error_msg.format(new_name, project))

        return new_name


class SaveAsSetAction(QueryAction):
    form_class = SaveAsSetForm
    output_types = (("text/html", "Result"),)

    def run(self, form):
        name = form.cleaned_data["name"]
        #provenance = form.cleaned_data["provenance"]
        project = form.cleaned_data["project"]
        aset = ArticleSet.objects.create(name=name, project=project)
        self.monitor.update(10, "Executing query..")
        article_ids = list(SelectionSearch(form).get_article_ids())
        self.monitor.update(60, "Saving to set..")
        aset.add_articles(article_ids)

        return OK_TEMPLATE.render(Context({
            "project": project,
            "aset": aset,
            "len": len(article_ids)
        }))

