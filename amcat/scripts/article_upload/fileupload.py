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

"""
Helper form for file upload forms that handles decoding and zip files
"""

import logging; log = logging.getLogger(__name__)
from django import forms
import os.path
import zipfile
import chardet
import csv
import collections
from contextlib import contextmanager
from django.core.files import File
import io
import tempfile
import shutil

@contextmanager
def TemporaryFolder(*args, **kargs):
    tempdir = tempfile.mkdtemp(*args, **kargs)
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)
        

DecodedFile = collections.namedtuple("File", ["name", "file", "bytes", "encoding", "text"])
ENCODINGS = ["Autodetect", "ISO-8859-15", "UTF-8", "Latin-1"]


class RawFileUploadForm(forms.Form):
    """Helper form to handle uploading a file"""
    file = forms.FileField(help_text="Uploading very large files can take a long time. If you encounter timeout problems, consider uploading smaller files")

    def get_entries(self):
        return [self.files['file']]
    
class FileUploadForm(RawFileUploadForm):
    """Helper form to handle uploading a file with encoding"""
    encoding = forms.ChoiceField(choices=enumerate(ENCODINGS),
                                 initial=0, required=False, 
                                 help_text="Try to change this value when character issues arise.", )

    
    def decode(self, bytes):
        """
        Decode the given bytes using the encoding specified in the form.
        If encoding is Autodetect, use (1) utf-8, (2) chardet, (3) latin-1.
        Returns a tuple (encoding, text) where encoding is the actual encoding used.
        """
        enc = ENCODINGS[int(self.cleaned_data['encoding'] or 0)]
        if enc != 'Autodetect':
            return enc, bytes.decode(enc)
        try:
            return "utf-8", bytes.decode('utf-8')
        except UnicodeDecodeError:
            pass
        enc = chardet.detect(bytes)["encoding"]
        if enc:
            try:
                return enc, bytes.decode(enc)
            except UnicodeDecodeError:
                pass
        return 'latin-1', bytes.decode('latin-1')

    def decode_file(self, f):
        enc, text = self.decode(f.read())
        if isinstance(f.file, io.BytesIO) and f.file.seekable():
            f.seek(0)
            return File(io.TextIOWrapper(f.file, encoding=enc), name=f.name)
        name = f.file.name if isinstance(f, File) else f.name
        return File(open(name, "r", encoding=enc), name=f.name)

    def get_uploaded_text(self):
        """Returns a DecodedFile object representing the file"""
        return self.decode_file(self.files['file'])
        
    def get_entries(self):
        return [self.get_uploaded_text()]
    
DIALECTS = [("autodetect", "Autodetect"),
            ("excel", "CSV, comma-separated"),
            ("excel-semicolon", "CSV, semicolon-separated (Europe)"),
            ]

class excel_semicolon(csv.excel):
    delimiter = ';'
csv.register_dialect("excel-semicolon", excel_semicolon)

def namedtuple_csv_reader(csv_file, encoding='utf-8', **kargs):
    """
    Wraps around a csv.reader object to yield namedtuples for the rows.
    Expects the first line to be the header.
    @params encoding: This encoding will be used to decode all values. If None, will yield raw bytes
     If encoding is an empty string or  'Autodetect', use chardet to guess the encoding
    @params object_name: The class name for the namedtuple
    @param kargs: Will be passed to csv.reader, e.g. dialect
    """
    if encoding.lower() in ('', 'autodetect'):
        encoding = chardet.detect(csv_file.read(1024))["encoding"]
        log.info("Guessed encoding: {encoding}".format(**locals()))
        csv_file.seek(0)
    
    r = csv.reader(csv_file, **kargs)
    return namedtuples_from_reader(r, encoding=encoding)


def _xlsx_as_csv(file):
    """
    Supply a csv reader-like interface to an xlsx file
    """
    from openpyxl import load_workbook
    wb = load_workbook(file)
    ws = wb.get_sheet_by_name(wb.get_sheet_names()[0])
    for row in ws.rows:
        row = [c.value for c in row]
        yield row
    
def namedtuple_xlsx_reader(xlsx_file):
    """
    Uses openpyxl to read an xslx file and provide a named-tuple interface to it
    """
    reader = _xlsx_as_csv(xlsx_file)
    return namedtuples_from_reader(reader)

def namedtuples_from_reader(reader, encoding=None):
    """
    returns a sequence of namedtuples from a (csv-like) reader which should yield the header followed by value rows
    """
    
    header = next(iter(reader))
    class Row(collections.namedtuple("Row", header, rename=True)):
        column_names=header
        def __getitem__(self, key):
            if not isinstance(key, int):
                # look up key in self.header
                key = self.column_names.index(key)
            return super(Row, self).__getitem__(key)
        def items(self):
            return zip(self.column_names, self)
        
    for values in reader:
        if encoding is not None:
            values = [x.decode(encoding) if isinstance(x, bytes) else x for x in values]
        if len(values) < len(header):
            values += [None] * (len(header) - len(values))
        yield Row(*values)
    
        
class CSVUploadForm(FileUploadForm):
    dialect = forms.ChoiceField(choices=DIALECTS, initial="autodetect", required=False, 
                                help_text="Select the kind of CSV file")

    def get_entries(self):
        return self.get_reader(reader_class=namedtuple_csv_reader)
    
    def get_reader(self, reader_class=namedtuple_csv_reader):
        file = self.decode_file(self.files['file'])
        
        if file.name.endswith(".xlsx"):
            if reader_class != namedtuple_csv_reader:
                raise ValueError("Cannot handle xlsx files with non-default reader, sorry!")
            return namedtuple_xlsx_reader(file)

        d = self.cleaned_data['dialect'] or "autodetect"

        if d == 'autodetect':
            dialect = csv.Sniffer().sniff(file.readline())
            file.seek(0)
            if dialect.delimiter not in "\t,;":
                dialect = csv.get_dialect('excel')
        else:
            dialect = csv.get_dialect(d)

        return reader_class(file, dialect=dialect)


class ZipFileUploadForm(FileUploadForm):
    file = forms.FileField(help_text="You can also upload a zip file containing the desired files. Uploading very large files can take a long time. If you encounter timeout problems, consider uploading smaller files")
        
    def get_uploaded_texts(self):
        """
        Returns a list of DecodedFile objects representing the zipped files,
        or just a [DecodedFile] if the uploaded file was not a .zip file.
        """
        f = self.files['file']
        extension = os.path.splitext(f.name)[1]
        if extension == ".zip":
            return [self.decode_file(f) for f in self.iter_zip_file_contents(f)]
        else:
            return [self.decode_file(f)]

    def get_entries(self):
        return self.get_uploaded_texts()

    def iter_zip_file_contents(self, zip_file, *args, **kargs):
        """
        Generator that unpacks and yields the zip entries as File objects. Skips folders.
        @param zip_file: The zip file to iterate over.
        @param args: Is passed to the `TemporaryFolder`
        @param kargs: Is passed to the `TemporaryFolder`
        """
        with TemporaryFolder(*args, **kargs) as tempdir:
            with zipfile.ZipFile(zip_file) as zf:
                for name in zf.namelist():
                    if name.endswith("/"): continue # skip folders
                    fn = os.path.basename(name)
                    # use mkstemp instead of temporary folder because we don't want it to be deleted
                    # it will be deleted on __exit__ anyway since the whole tempdir will be deleted
                    _handle, fn = tempfile.mkstemp(suffix="_"+fn, dir=tempdir)
                    f = open(fn, 'wb')
                    shutil.copyfileobj(zf.open(name), f)
                    f.close()

                    with open(os.path.join(tempdir, fn), "rb") as fh:
                        yield File(fh, name=name)



