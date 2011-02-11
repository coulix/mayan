from django.utils.translation import ugettext as _
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.contrib import messages
from django.views.generic.list_detail import object_detail, object_list
from django.core.urlresolvers import reverse
from django.views.generic.create_update import create_object, delete_object, update_object
#from django.forms.formsets import formset_factory
from django.core.files.base import File
from django.conf import settings
from django.utils.http import urlencode
from django.template.defaultfilters import slugify

from filetransfers.api import serve_file
from converter.api import convert, in_image_cache
from common.utils import pretty_size

from utils import from_descriptor_to_tempfile

from models import Document, DocumentMetadata, DocumentType, MetadataType
from forms import DocumentTypeSelectForm, DocumentCreateWizard, \
        MetadataForm, DocumentForm, DocumentForm_edit, DocumentForm_view, \
        StagingDocumentForm, DocumentTypeMetadataType, DocumentPreviewForm, \
        MetadataFormSet
    
from staging import StagingFile

from documents.conf.settings import DELETE_STAGING_FILE_AFTER_UPLOAD
from documents.conf.settings import USE_STAGING_DIRECTORY
from documents.conf.settings import FILESYSTEM_FILESERVING_ENABLE
from documents.conf.settings import STAGING_FILES_PREVIEW_SIZE
from documents.conf.settings import PREVIEW_SIZE
from documents.conf.settings import THUMBNAIL_SIZE

from utils import save_metadata, save_metadata_list, decode_metadata_from_url

def document_list(request):
    return object_list(
        request,
        queryset=Document.objects.all(),
        template_name='generic_list.html',
        extra_context={
            'title':_(u'documents'),
        },
    )

def document_create(request, multiple=True):
    if DocumentType.objects.all().count() == 1:
        wizard = DocumentCreateWizard(
            document_type=DocumentType.objects.all()[0],
            form_list=[MetadataFormSet], multiple=multiple,
            step_titles = [
            _(u'document metadata'),
            ])
    else:
        wizard = DocumentCreateWizard(form_list=[DocumentTypeSelectForm, MetadataFormSet], multiple=multiple)
        
    return wizard(request)

def document_create_sibling(request, document_id, multiple=True):
    document = get_object_or_404(Document, pk=document_id)
    urldata = []
    for id, metadata in enumerate(document.documentmetadata_set.all()):
        if hasattr(metadata, 'value'):
            urldata.append(('metadata%s_id' % id,metadata.metadata_type.id))   
            urldata.append(('metadata%s_value' % id,metadata.value))
        
    if multiple:
        view = 'upload_multiple_documents_with_type'
    else:
        view = 'upload_document_with_type'
    
    url = reverse(view, args=[document.document_type.id])
    return HttpResponseRedirect('%s?%s' % (url, urlencode(urldata)))


def upload_document_with_type(request, document_type_id, multiple=True):
    document_type = get_object_or_404(DocumentType, pk=document_type_id)
    local_form = DocumentForm(prefix='local', initial={'document_type':document_type})
    if USE_STAGING_DIRECTORY:
        staging_form = StagingDocumentForm(prefix='staging', 
            initial={'document_type':document_type})
    
    if request.method == 'POST':
        if 'local-submit' in request.POST.keys():
            local_form = DocumentForm(request.POST, request.FILES,
                prefix='local', initial={'document_type':document_type})
            if local_form.is_valid():
                instance = local_form.save()
                instance.update_checksum()
                instance.update_mimetype()
                if 'document_type_available_filenames' in local_form.cleaned_data:
                    if local_form.cleaned_data['document_type_available_filenames']:
                        instance.file_filename = local_form.cleaned_data['document_type_available_filenames'].filename
                        instance.save()
            
                save_metadata_list(decode_metadata_from_url(request.GET), instance)
                messages.success(request, _(u'Document uploaded successfully.'))
                try:
                    instance.create_fs_links()
                except Exception, e:
                    messages.error(request, e)
                    
                if multiple:
                    return HttpResponseRedirect(request.get_full_path())
                else:
                    return HttpResponseRedirect(reverse('document_list'))
        elif 'staging-submit' in request.POST.keys() and USE_STAGING_DIRECTORY:
            staging_form = StagingDocumentForm(request.POST, request.FILES,
                prefix='staging', initial={'document_type':document_type})
            if staging_form.is_valid():
                staging_file_id = staging_form.cleaned_data['staging_file_id']
                
                try:
                    staging_file = StagingFile.get(staging_file_id)
                except Exception, e:
                    messages.error(request, e)   
                else:
                    try:
                        document = Document(file=staging_file.upload(), document_type=document_type)
                        document.save()
                        document.update_checksum()
                        document.update_mimetype()
                    except Exception, e:
                        messages.error(request, e)   
                    else:
                        
                        if 'document_type_available_filenames' in staging_form.cleaned_data:
                            if staging_form.cleaned_data['document_type_available_filenames']:
                                document.file_filename = staging_form.cleaned_data['document_type_available_filenames'].filename
                                document.save()
                                                
                        save_metadata_list(decode_metadata_from_url(request.GET), document)
                        messages.success(request, _(u'Staging file: %s, uploaded successfully.') % staging_file.filename)
                        try:
                            document.create_fs_links()
                        except Exception, e:
                            messages.error(request, e)
                
                        if DELETE_STAGING_FILE_AFTER_UPLOAD:
                            try:
                                staging_file.delete()
                                messages.success(request, _(u'Staging file: %s, deleted successfully.') % staging_file.filename)
                            except Exception, e:
                                messages.error(request, e)

            if multiple:
                return HttpResponseRedirect(request.META['HTTP_REFERER'])
            else:
                return HttpResponseRedirect(reverse('document_list'))                


    context = {
        'document_type_id':document_type_id,
        'form_list':[
            {
                'form':local_form,
                'title':_(u'upload a local document'),
                'grid':6,
                'grid_clear':False if USE_STAGING_DIRECTORY else True,
            },
        ],
    }
    
    if USE_STAGING_DIRECTORY:
        try:
            filelist = StagingFile.get_all()
        except Exception, e:
            messages.error(request, e)
            filelist = []
        finally:
            context.update({
                'subtemplates_dict':[
                    {
                        'name':'generic_list_subtemplate.html',
                        'title':_(u'files in staging'),
                        'object_list':filelist,
                        'hide_link':True,
                    },
                ],
            })
            context['form_list'].append(
                {
                    'form':staging_form,
                    'title':_(u'upload a document from staging'),
                    'grid':6,
                    'grid_clear':True,   
                },
            )
    
    return render_to_response('generic_form.html', context,
        context_instance=RequestContext(request))
        
        
def document_view(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    form = DocumentForm_view(instance=document, extra_fields=[
        {'label':_(u'Filename'), 'field':'file_filename'},
        {'label':_(u'File extension'), 'field':'file_extension'},
        {'label':_(u'File mimetype'), 'field':'file_mimetype'},
        {'label':_(u'File mime encoding'), 'field':'file_mime_encoding'},
        {'label':_(u'File size'), 'field':lambda x: pretty_size(x.file.storage.size(x.file.path)) if x.exists() else '-'},
        {'label':_(u'Exists in storage'), 'field':'exists'},
        {'label':_(u'Date added'), 'field':lambda x: x.date_added.date()},
        {'label':_(u'Time added'), 'field':lambda x: unicode(x.date_added.time()).split('.')[0]},
        {'label':_(u'Checksum'), 'field':'checksum'},
        {'label':_(u'UUID'), 'field':'uuid'},
    ])
    
    preview_form = DocumentPreviewForm(document=document)
    form_list = [
        {
            'form':form,
            'object':document,
            'grid':6,
        },
        {
            'form':preview_form,
            'title':_(u'document preview'),
            'object':document,
            'grid':6,
            'grid_clear':True,
        },
    ]
    subtemplates_dict = [
            {
                'name':'generic_list_subtemplate.html',
                'title':_(u'metadata'),
                'object_list':document.documentmetadata_set.all(),
                'extra_columns':[{'name':_(u'value'), 'attribute':'value'}],
                'hide_link':True,
            },
        ]
    
    if FILESYSTEM_FILESERVING_ENABLE:
        subtemplates_dict.append({
            'name':'generic_list_subtemplate.html',
            'title':_(u'index links'),
            'object_list':document.documentmetadataindex_set.all(),
            'hide_link':True})
    
    return render_to_response('generic_detail.html', {
        'form_list':form_list,
        'object':document,
        'subtemplates_dict':subtemplates_dict,
    }, context_instance=RequestContext(request))


def document_delete(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
        
    return delete_object(request, model=Document, object_id=document_id, 
        template_name='generic_confirm.html', 
        post_delete_redirect=reverse('document_list'),
        extra_context={
            'delete_view':True,
            'object':document,
            'object_name':_(u'document'),
        })
        
        
def document_edit(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    if request.method == 'POST':
        form = DocumentForm_edit(request.POST, initial={'document_type':document.document_type})
        if form.is_valid():
            try:
                document.delete_fs_links()
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(reverse('document_list'))

            document.file_filename = form.cleaned_data['new_filename']

            if 'document_type_available_filenames' in form.cleaned_data:
                if form.cleaned_data['document_type_available_filenames']:
                    document.file_filename = form.cleaned_data['document_type_available_filenames'].filename
                
            document.save()
            
            messages.success(request, _(u'Document %s edited successfully.') % document)
            
            try:
                document.create_fs_links()
                messages.success(request, _(u'Document filesystem links updated successfully.'))                
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(document.get_absolute_url())
                
            return HttpResponseRedirect(document.get_absolute_url())
    else:
        form = DocumentForm_edit(instance=document, initial={
            'new_filename':document.file_filename, 'document_type':document.document_type})

    return render_to_response('generic_form.html', {
        'form':form,
        'object':document,
    
    }, context_instance=RequestContext(request))


def document_edit_metadata(request, document_id):
    document = get_object_or_404(Document, pk=document_id)

    initial=[]
    for item in DocumentTypeMetadataType.objects.filter(document_type=document.document_type):
        initial.append({
            'metadata_type':item.metadata_type,
            'document_type':document.document_type,
            'value':document.documentmetadata_set.get(metadata_type=item.metadata_type).value if document.documentmetadata_set.filter(metadata_type=item.metadata_type) else None
        })
    #for metadata in document.documentmetadata_set.all():
    #    initial.append({
    #        'metadata_type':metadata.metadata_type,
    #        'document_type':document.document_type,
    #        'value':metadata.value,
    #    })    

    formset = MetadataFormSet(initial=initial)
    if request.method == 'POST':
        formset = MetadataFormSet(request.POST)
        if formset.is_valid():
            save_metadata_list(formset.cleaned_data, document)
            try:
                document.delete_fs_links()
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(reverse('document_list'))
           
            messages.success(request, _(u'Metadata for document %s edited successfully.') % document)
            
            try:
                document.create_fs_links()
                messages.success(request, _(u'Document filesystem links updated successfully.'))                
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(document.get_absolute_url())
                
            return HttpResponseRedirect(document.get_absolute_url())
        
        
    return render_to_response('generic_form.html', {
        'form_display_mode_table':True,
        'form':formset,
        'object':document,
    
    }, context_instance=RequestContext(request))
    

def get_document_image(request, document_id, size=PREVIEW_SIZE):
    document = get_object_or_404(Document, pk=document_id)
    
    try:
        filepath = in_image_cache(document.checksum, size)
        if filepath:
            return serve_file(request, File(file=open(filepath, 'r')))
        
        #Save to a temporary location
        document.file.open()
        desc = document.file.storage.open(document.file.path)
        filepath = from_descriptor_to_tempfile(desc, document.checksum)
        output_file = convert(filepath, size, mimetype=document.file_mimetype, extension=document.file_extension)
        return serve_file(request, File(file=open(output_file, 'r')))
    except Exception, e:
        if size == THUMBNAIL_SIZE:
            return serve_file(request, File(file=open('%simages/picture_error.png' % settings.MEDIA_ROOT, 'r')))
        else:
            return serve_file(request, File(file=open('%simages/1297211435_error.png' % settings.MEDIA_ROOT, 'r')))

        
def document_download(request, document_id):
    document = get_object_or_404(Document, pk=document_id)
    try:
        #Test permissions and trigger exception
        document.file.open()
        return serve_file(request, document.file, save_as='%s' % document.get_fullname())
    except Exception, e:
        messages.error(request, e)
        return HttpResponseRedirect(request.META['HTTP_REFERER'])


def staging_file_preview(request, staging_file_id):
    try:
        filepath = StagingFile.get(staging_file_id).filepath
        output_file = convert(filepath, STAGING_FILES_PREVIEW_SIZE)
        return serve_file(request, File(file=open(output_file, 'r')))
    except Exception, e:
        return serve_file(request, File(file=open('%simages/1297211435_error.png' % settings.MEDIA_ROOT, 'r')))        
     
