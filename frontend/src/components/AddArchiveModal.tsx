import { useState, useRef } from 'react';
import { Upload, X, Loader2, Sparkles } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalTitle } from './ui/modal';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { Progress } from './ui/progress';
import type { ArchiveItem } from '../App';
import { toast } from 'sonner';
import { createArchive, generateMetadata } from '../services/api';

type AddArchiveModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (item: ArchiveItem) => void;
};

export function AddArchiveModal({ isOpen, onClose, onAdd }: AddArchiveModalProps) {
  const [formData, setFormData] = useState({
    title: '',
    type: 'image' as ArchiveItem['type'],
    date: new Date().toISOString().split('T')[0],
    tags: '',
    description: '',
  });
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isGeneratingMetadata, setIsGeneratingMetadata] = useState(false);
  const [metadataGenerated, setMetadataGenerated] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleGenerateMetadata = async (files: File[]) => {
    if (files.length === 0) {
      return;
    }

    setIsGeneratingMetadata(true);

    try {
      // Determine media types from files
      const mediaTypes = determineMediaTypes(files);

      // Call API to generate metadata
      const metadata = await generateMetadata(files, mediaTypes);

      // Update form data with generated metadata
      setFormData(prev => ({
        ...prev,
        title: metadata.title,
        tags: metadata.tags.join(', '),
        description: metadata.description,
      }));

      setMetadataGenerated(true);
      toast.success('AI has auto-filled title, tags, and description. You can edit them if needed.');
    } catch (error) {
      console.error('Error generating metadata:', error);
      toast.error(
        error instanceof Error
          ? error.message
          : 'Failed to generate metadata suggestions.'
      );
    } finally {
      setIsGeneratingMetadata(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      setSelectedFiles(filesArray);
      setMetadataGenerated(false);
      
      // Automatically generate metadata
      await handleGenerateMetadata(filesArray);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    // Reset metadata generated flag when files change
    setMetadataGenerated(false);
  };

  const getFileType = (file: File): ArchiveItem['type'] => {
    const type = file.type.split('/')[0];
    if (type === 'image') return 'image';
    if (type === 'video') return 'video';
    if (type === 'audio') return 'audio';
    return 'document';
  };

  const determineMediaTypes = (files: File[]): ArchiveItem['type'][] => {
    const types = new Set<ArchiveItem['type']>();
    files.forEach((file) => {
      types.add(getFileType(file));
    });
    return Array.from(types);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.title.trim()) {
      toast.error('Please enter a title');
      return;
    }

    if (selectedFiles.length === 0) {
      toast.error('Please select at least one file to upload');
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Determine media types from files
      const mediaTypes = determineMediaTypes(selectedFiles);
      
      // Parse tags
      const tags = formData.tags
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean);

      // Parse dates (use form date or current date)
      const dates = formData.date ? [formData.date] : [];

      // Simulate progress updates
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 500);

      // Call API to create archive
      const response = await createArchive({
        files: selectedFiles,
        title: formData.title,
        media_types: mediaTypes,
        tags: tags.length > 0 ? tags : undefined,
        description: formData.description || undefined,
        dates: dates.length > 0 ? dates : undefined,
      });

      clearInterval(progressInterval);
      setUploadProgress(100);

      // Map backend response to frontend ArchiveItem format
      // Use first file URI as fileUrl, or first file_uri from response
      const fileUrl = response.file_uris && response.file_uris.length > 0 
        ? response.file_uris[0] 
        : 'https://via.placeholder.com/400';
      
      // Use first media type or default to the selected type
      const primaryType = response.media_types && response.media_types.length > 0
        ? response.media_types[0]
        : formData.type;

      // Use first date or form date
      const date = response.dates && response.dates.length > 0
        ? response.dates[0].split('T')[0]
        : formData.date;

      const newItem: ArchiveItem = {
        id: response.id,
        title: response.title,
        type: primaryType,
        date: date,
        tags: response.tags || [],
        description: response.description || '',
        fileUrl: fileUrl,
        thumbnail: primaryType === 'image' ? fileUrl : undefined,
        file_uris: response.file_uris,
      };

      onAdd(newItem);
      toast.success('Archive item added successfully! AI analysis complete.');

      // Reset form
      setFormData({
        title: '',
        type: 'image',
        date: new Date().toISOString().split('T')[0],
        tags: '',
        description: '',
      });
      setSelectedFiles([]);
      setUploadProgress(0);
      setMetadataGenerated(false);
      onClose();
    } catch (error) {
      console.error('Error creating archive:', error);
      toast.error(
        error instanceof Error
          ? error.message
          : 'Failed to create archive. Please try again.'
      );
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} className="max-w-2xl">
      <ModalHeader onClose={onClose}>
        <ModalTitle>Add New Archive Item</ModalTitle>
      </ModalHeader>

      <ModalBody>
        <form id="archive-form" onSubmit={handleSubmit} className="space-y-4 py-6">
          {/* File Upload */}
          <div>
            <Label>Upload Files *</Label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="mt-2 border-2 border-dashed border-stone-300 rounded-lg p-8 text-center cursor-pointer hover:border-forest hover:bg-stone-50 transition-colors"
            >
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
                accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt"
                multiple
              />
              
              {selectedFiles.length > 0 ? (
                <div className="space-y-2">
                  {selectedFiles.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 bg-stone-50 rounded border border-stone-200"
                    >
                      <div className="text-left flex-1">
                        <p className="text-sm text-stone-700 font-medium">{file.name}</p>
                        <p className="text-xs text-stone-500">
                          {(file.size / 1024 / 1024).toFixed(2)} MB • {getFileType(file)}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={(e: React.MouseEvent) => {
                          e.stopPropagation();
                          removeFile(index);
                        }}
                        className="ml-2"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={(e: React.MouseEvent) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                    className="mt-2"
                  >
                    Add More Files
                  </Button>
                </div>
              ) : (
                <div>
                  <Upload className="w-8 h-8 text-stone-400 mx-auto mb-2" />
                  <p className="text-sm text-stone-600">Click to upload files</p>
                  <p className="text-xs text-stone-500 mt-1">
                    Images, Videos, Audio, Documents (multiple files supported)
                  </p>
                </div>
              )}
            </div>
            
            {isGeneratingMetadata && (
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-stone-600 flex items-center">
                    <Sparkles className="w-4 h-4 mr-2 text-forest" />
                    Generating metadata suggestions...
                  </span>
                </div>
                <Progress value={50} className="mt-2" />
                <p className="text-xs text-stone-500">
                  AI is analyzing your files to suggest title, tags, and description.
                </p>
              </div>
            )}
            
            {isUploading && (
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-stone-600">Uploading and analyzing...</span>
                  <span className="text-stone-500">{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} className="mt-2" />
                <p className="text-xs text-stone-500">
                  This may take a few moments. AI is analyzing your content.
                </p>
              </div>
            )}
          </div>

          {/* Title */}
          <div>
            <Label htmlFor="title" className="flex items-center gap-2">
              Title *
              {metadataGenerated && (
                <span className="text-xs text-forest font-normal flex items-center">
                  <Sparkles className="w-3 h-3 mr-1" />
                  AI-generated
                </span>
              )}
            </Label>
            <Input
              id="title"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Traditional Batik Pattern"
              required
              disabled={isGeneratingMetadata}
            />
          </div>

          {/* Date */}
          <div>
            <Label htmlFor="date">Date</Label>
            <Input
              id="date"
              type="date"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
            />
            <p className="text-xs text-stone-500 mt-1">
              Media types will be automatically detected from uploaded files
            </p>
          </div>

          {/* Tags */}
          <div>
            <Label htmlFor="tags" className="flex items-center gap-2">
              Tags
              {metadataGenerated && (
                <span className="text-xs text-forest font-normal flex items-center">
                  <Sparkles className="w-3 h-3 mr-1" />
                  AI-generated
                </span>
              )}
            </Label>
            <Input
              id="tags"
              value={formData.tags}
              onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
              placeholder="batik, heritage, traditional (comma separated)"
              disabled={isGeneratingMetadata}
            />
          </div>

          {/* Description */}
          <div>
            <Label htmlFor="description" className="flex items-center gap-2">
              Description
              {metadataGenerated && (
                <span className="text-xs text-forest font-normal flex items-center">
                  <Sparkles className="w-3 h-3 mr-1" />
                  AI-generated
                </span>
              )}
            </Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Describe the archive item..."
              rows={4}
              disabled={isGeneratingMetadata}
            />
          </div>
        </form>
      </ModalBody>

      <ModalFooter>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="archive-form" disabled={isUploading} className="bg-forest hover:bg-forest">
            {isUploading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              'Add to Archive'
            )}
          </Button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
