/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {Component, OnInit, OnDestroy, signal, computed} from '@angular/core';
import {MatDialog} from '@angular/material/dialog';
import {Subscription, timer, of, throwError} from 'rxjs';
import {switchMap, catchError} from 'rxjs/operators';
import {ImageSelectorComponent} from '../../common/components/image-selector/image-selector.component';
import {SubtitlesService, SubtitleResponse} from './subtitles.service';

export type InputSourceTab = 'upload' | 'gallery' | 'url';
export type SubtitleStep =
  | 'idle'
  | 'uploading'
  | 'extracting'
  | 'transcribing'
  | 'formatting'
  | 'packaging'
  | 'completed'
  | 'failed';

@Component({
  selector: 'app-subtitles',
  templateUrl: './subtitles.component.html',
  styleUrls: ['./subtitles.component.scss'],
})
export class SubtitlesComponent implements OnInit, OnDestroy {
  constructor(
    private dialog: MatDialog,
    private subtitlesService: SubtitlesService,
  ) {}

  // Navigation & Input Signals
  readonly activeTab = signal<InputSourceTab>('upload');
  readonly selectedFile = signal<File | null>(null);
  readonly selectedGalleryAsset = signal<{
    id: string;
    title: string;
    url: string;
  } | null>(null);
  readonly videoUrl = signal<string>('');

  // Configuration Signals
  readonly packageName = signal<string>('');
  readonly sourceLanguage = signal<string>('en-US');
  readonly enableDynamicSubtitles = signal<boolean>(true);
  readonly enableBurnedInVideo = signal<boolean>(false);
  readonly subtitleStylePreset = signal<'minimal' | 'tiktok' | 'box' | 'neon'>(
    'minimal',
  );

  // Processing & Step Signals
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<SubtitleStep>('idle');
  readonly progressPercentage = signal<number>(0);
  readonly isDraggingOver = signal<boolean>(false);
  readonly previewVideoUrl = signal<string | null>(null);
  readonly savedToGallery = signal<boolean>(false);
  readonly savedPackageName = signal<string>('');
  readonly localOutputDir = signal<string | null>(null);
  readonly activeJobId = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);

  private pollSubscription?: Subscription;

  readonly statusDescription = computed(() => {
    switch (this.processingStep()) {
      case 'uploading':
        return 'Uploading source media to server...';
      case 'extracting':
        return 'Extracting high-fidelity audio stream...';
      case 'transcribing':
        return 'Transcribing speech with STT v2 chirp_3...';
      case 'formatting':
        return 'Refining formatting with Gemini (<= 42 chars/line)...';
      case 'packaging':
        return 'Embedding tracks and exporting MP4/VTT/SRT...';
      case 'completed':
        return 'Package generated successfully!';
      case 'failed':
        return 'Subtitle generation encountered an error.';
      default:
        return 'Idle';
    }
  });

  readonly availableLanguages = [
    {code: 'en-US', label: 'English (US)'},
    {code: 'es-ES', label: 'Spanish'},
    {code: 'fr-FR', label: 'French'},
    {code: 'de-DE', label: 'German'},
    {code: 'ja-JP', label: 'Japanese'},
    {code: 'pt-BR', label: 'Portuguese (Brazil)'},
  ];

  // Computed Signals
  readonly hasInput = computed(() => {
    if (this.activeTab() === 'upload') return !!this.selectedFile();
    if (this.activeTab() === 'gallery') return !!this.selectedGalleryAsset();
    if (this.activeTab() === 'url') return !!this.videoUrl().trim();
    return false;
  });

  readonly hasValidOutput = computed(() => {
    return this.enableDynamicSubtitles() || this.enableBurnedInVideo();
  });

  readonly isComplete = computed(() => this.processingStep() === 'completed');

  readonly suggestedPackageName = computed(() => {
    let baseName = 'Media Track';
    if (this.selectedFile()) {
      baseName = this.selectedFile()!.name.replace(/\.[^/.]+$/, '');
    } else if (this.selectedGalleryAsset()) {
      baseName = this.selectedGalleryAsset()!.title.replace(/\.[^/.]+$/, '');
    } else if (this.videoUrl().trim()) {
      baseName = 'Web Video';
    }
    const langCode = this.sourceLanguage().split('-')[0].toUpperCase();
    return `${baseName} - Subtitles [${langCode}]`;
  });

  readonly currentPackageDisplayName = computed(() => {
    return this.packageName().trim() || this.suggestedPackageName();
  });

  ngOnInit(): void {}

  ngOnDestroy(): void {
    this.stopPolling();
    this.cleanupPreviewUrl();
  }

  private cleanupPreviewUrl(): void {
    const current = this.previewVideoUrl();
    if (current && current.startsWith('blob:')) {
      try {
        if (typeof window !== 'undefined' && window.URL) {
          window.URL.revokeObjectURL(current);
        }
      } catch (err) {
        console.debug('Failed to revoke object URL', err);
      }
    }
  }

  private stopPolling(): void {
    if (this.pollSubscription) {
      this.pollSubscription.unsubscribe();
      this.pollSubscription = undefined;
    }
  }

  setActiveTab(tab: InputSourceTab): void {
    this.activeTab.set(tab);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      this.previewVideoUrl.set(
        typeof window !== 'undefined' && window.URL
          ? window.URL.createObjectURL(file)
          : '',
      );
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
      input.value = '';
    }
  }

  openGallerySelector(): void {
    const dialogRef = this.dialog.open(ImageSelectorComponent, {
      width: '90vw',
      height: '80vh',
      maxWidth: '90vw',
      data: {
        mimeType: 'video/*',
        showFooter: true,
        maxSelection: 1,
      },
      panelClass: 'image-selector-dialog',
    });

    dialogRef.afterClosed().subscribe((result: Record<string, any> | null) => {
      if (result) {
        let title = 'Selected Gallery Asset';
        let url = '';
        if ('original_filename' in result) {
          title = String(result['original_filename']);
          url = String(result['gcs_uri'] || '');
        } else if ('mediaItem' in result && result['mediaItem']) {
          const item = result['mediaItem'];
          title = item.title || item.filename || 'Gallery Video';
          url = item.gcs_uri || item.url || '';
        } else if (typeof result === 'object' && result['title']) {
          title = String(result['title']);
          url = String(result['url'] || result['gcs_uri'] || '');
        }
        this.selectGalleryAsset({
          id: String(result['id'] || 'gallery-selected'),
          title: title || 'Media Gallery Video',
          url:
            url ||
            'https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
        });
      }
    });
  }

  selectGalleryAsset(asset: {id: string; title: string; url: string}): void {
    this.cleanupPreviewUrl();
    this.selectedGalleryAsset.set(asset);
    this.previewVideoUrl.set(asset.url);
    this.selectedFile.set(null);
    this.videoUrl.set('');
  }

  onUrlChange(url: string): void {
    this.videoUrl.set(url);
    if (url.trim()) {
      this.cleanupPreviewUrl();
      this.selectedFile.set(null);
      this.selectedGalleryAsset.set(null);
      this.previewVideoUrl.set(null);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDraggingOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);
    if (event.dataTransfer && event.dataTransfer.files.length > 0) {
      const file = event.dataTransfer.files[0];
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      this.previewVideoUrl.set(
        typeof window !== 'undefined' && window.URL
          ? window.URL.createObjectURL(file)
          : '',
      );
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
    }
  }

  toggleDynamicSubtitles(): void {
    this.enableDynamicSubtitles.update(val => !val);
  }

  toggleBurnedInVideo(): void {
    this.enableBurnedInVideo.update(val => !val);
  }

  setLanguage(lang: string): void {
    this.sourceLanguage.set(lang);
  }

  setStylePreset(preset: 'minimal' | 'tiktok' | 'box' | 'neon'): void {
    this.subtitleStylePreset.set(preset);
  }

  clearSelection(): void {
    this.resetStudio();
  }

  resetStudio(): void {
    this.stopPolling();
    this.cleanupPreviewUrl();
    this.selectedFile.set(null);
    this.selectedGalleryAsset.set(null);
    this.videoUrl.set('');
    this.packageName.set('');
    this.previewVideoUrl.set(null);
    this.processingStep.set('idle');
    this.progressPercentage.set(0);
    this.isProcessing.set(false);
    this.savedToGallery.set(false);
    this.savedPackageName.set('');
    this.localOutputDir.set(null);
    this.activeJobId.set(null);
    this.errorMessage.set(null);
  }

  startGeneration(): void {
    if (!this.hasInput() || !this.hasValidOutput() || this.isProcessing())
      return;

    this.stopPolling();
    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.progressPercentage.set(10);
    this.savedToGallery.set(false);
    this.errorMessage.set(null);

    const videoSource =
      this.activeTab() === 'gallery'
        ? this.selectedGalleryAsset()?.url
        : this.activeTab() === 'url'
          ? this.videoUrl()
          : undefined;

    const file = this.activeTab() === 'upload' ? this.selectedFile() : null;

    this.subtitlesService
      .generateSubtitles({
        file,
        videoUrl: videoSource,
        packageName: this.currentPackageDisplayName(),
        languageCode: this.sourceLanguage(),
        outputFormat: 'vtt',
        burnSubtitles: this.enableBurnedInVideo(),
      })
      .subscribe({
        next: (initRes: SubtitleResponse) => {
          this.activeJobId.set(initRes.job_id);
          this.localOutputDir.set(initRes.local_output_dir || null);

          if (initRes.status === 'completed') {
            this.handleJobCompletion(initRes);
            return;
          }

          if (initRes.status === 'failed') {
            this.handleJobFailure(
              initRes.error_message || 'Subtitle processing failed.',
            );
            return;
          }

          this.processingStep.set(
            (initRes.step as SubtitleStep) || 'extracting',
          );
          this.progressPercentage.set(initRes.progress || 15);
          this.startPollingStatus(initRes.job_id);
        },
        error: (err: HttpErrorResponse | Error | unknown) => {
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Failed to submit subtitle job.';
          this.handleJobFailure(detail || 'Failed to submit subtitle job.');
        },
      });
  }

  private startPollingStatus(jobId: string): void {
    this.stopPolling();
    let consecutiveErrors = 0;

    this.pollSubscription = timer(0, 1500)
      .pipe(
        switchMap(() =>
          this.subtitlesService.getJobStatus(jobId).pipe(
            catchError(err => {
              consecutiveErrors++;
              if (consecutiveErrors >= 6 || err?.status === 404) {
                return throwError(() => err);
              }
              return of(null);
            }),
          ),
        ),
      )
      .subscribe({
        next: (res: SubtitleResponse | null) => {
          if (!res) return;
          consecutiveErrors = 0;

          if (res.status === 'completed') {
            this.stopPolling();
            this.handleJobCompletion(res);
          } else if (res.status === 'failed') {
            this.stopPolling();
            this.handleJobFailure(
              res.error_message || 'Subtitle generation failed.',
            );
          } else {
            if (res.step) {
              this.processingStep.set(res.step as SubtitleStep);
            }
            if (typeof res.progress === 'number') {
              this.progressPercentage.set(res.progress);
            }
          }
        },
        error: (err: HttpErrorResponse | Error | unknown) => {
          this.stopPolling();
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Lost connection to subtitle tracking service.';
          this.handleJobFailure(
            detail || 'Lost connection to subtitle tracking service.',
          );
        },
      });
  }

  private handleJobCompletion(res: SubtitleResponse): void {
    this.processingStep.set('completed');
    this.progressPercentage.set(100);
    this.isProcessing.set(false);
    this.localOutputDir.set(res.local_output_dir || null);

    if (res.default_toggleable_video || res.burned_in_video) {
      this.cleanupPreviewUrl();
      this.previewVideoUrl.set(
        res.burned_in_video ||
          res.default_toggleable_video ||
          this.previewVideoUrl(),
      );
    }
  }

  private handleJobFailure(errorMsg: string): void {
    this.processingStep.set('failed');
    this.isProcessing.set(false);
    this.errorMessage.set(errorMsg);
  }

  downloadCaptions(type: 'vtt' | 'srt'): void {
    const jobId = this.activeJobId();
    if (!jobId) return;

    this.subtitlesService.downloadFile(jobId, type).subscribe({
      next: blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.currentPackageDisplayName()}.${type}`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: err => {
        this.errorMessage.set(
          `Failed to download .${type} file: ${err?.message || 'Server error'}`,
        );
      },
    });
  }

  downloadVideo(): void {
    const jobId = this.activeJobId();
    if (!jobId) return;

    const fileType = this.enableBurnedInVideo()
      ? 'burned_in_video'
      : 'toggleable_video';
    this.subtitlesService.downloadFile(jobId, fileType).subscribe({
      next: blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.currentPackageDisplayName()}.mp4`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: err => {
        this.errorMessage.set(
          `Failed to download MP4 video: ${err?.message || 'Server error'}`,
        );
      },
    });
  }

  saveToMediaGallery(): void {
    const pkgName = this.currentPackageDisplayName();
    this.savedPackageName.set(pkgName);
    this.savedToGallery.set(true);
  }
}
