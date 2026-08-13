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

import {isPlatformBrowser} from '@angular/common';
import {HttpErrorResponse} from '@angular/common/http';
import {
  Component,
  OnInit,
  OnDestroy,
  signal,
  computed,
  PLATFORM_ID,
  Inject,
  DestroyRef,
  inject,
  ViewChild,
  ElementRef,
} from '@angular/core';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {MatDialog} from '@angular/material/dialog';
import {ActivatedRoute} from '@angular/router';
import {Subscription, timer, of, throwError} from 'rxjs';
import {switchMap, catchError} from 'rxjs/operators';
import {ImageSelectorComponent} from '../../common/components/image-selector/image-selector.component';
import {WorkspaceStateService} from '../../services/workspace/workspace-state.service';
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
  private destroyRef = inject(DestroyRef);

  @ViewChild('burnedVideoPlayer')
  burnedVideoPlayerRef?: ElementRef<HTMLVideoElement>;
  @ViewChild('sourceVideoPlayer')
  sourceVideoPlayerRef?: ElementRef<HTMLVideoElement>;

  constructor(
    private dialog: MatDialog,
    private subtitlesService: SubtitlesService,
    private workspaceStateService: WorkspaceStateService,
    private route: ActivatedRoute,
    @Inject(PLATFORM_ID) private platformId: object,
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
  readonly enableBurnedInVideo = signal<boolean>(true);
  readonly subtitleStylePreset = signal<'minimal' | 'tiktok' | 'box' | 'neon'>(
    'minimal',
  );

  // Processing & Step Signals
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<SubtitleStep>('idle');
  readonly progressPercentage = signal<number>(0);
  readonly isDraggingOver = signal<boolean>(false);
  readonly sourceVideoPreviewUrl = signal<string | null>(null);
  readonly subtitledVideoPreviewUrl = signal<string | null>(null);
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

  readonly vttTrackUrl = computed(() => {
    const jid = this.activeJobId();
    if (jid && this.isComplete() && this.enableDynamicSubtitles()) {
      return this.subtitlesService.getDownloadUrl(jid, 'vtt');
    }
    return null;
  });

  ngOnInit(): void {
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(params => {
        const jobId = params.get('job_id');
        const gcsUri = params.get('gcs_uri');
        const videoUrl = params.get('video_url');
        const packageName =
          params.get('package_name') || params.get('title') || '';

        if (videoUrl) {
          this.sourceVideoPreviewUrl.set(videoUrl);
          this.previewVideoUrl.set(videoUrl);
        }
        if (packageName) {
          this.packageName.set(packageName);
        }

        if (jobId) {
          this.loadExistingJob(jobId);
        } else if (videoUrl) {
          if (packageName) {
            this.processingStep.set('completed');
            this.progressPercentage.set(100);
            this.isProcessing.set(false);
            this.enableBurnedInVideo.set(true);
            this.subtitledVideoPreviewUrl.set(videoUrl);
          }
          if (gcsUri) {
            this.activeTab.set('gallery');
            this.selectedGalleryAsset.set({
              id: 'gallery_source',
              title: packageName || 'Gallery Video',
              url: videoUrl,
            });
          }
        } else if (gcsUri) {
          this.activeTab.set('gallery');
          this.selectedGalleryAsset.set({
            id: 'gallery_source',
            title: packageName || 'Gallery Video',
            url: gcsUri,
          });
        }
      });
  }

  loadExistingJob(jobId: string): void {
    this.activeJobId.set(jobId);
    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.subtitlesService.getJobStatus(jobId).subscribe({
      next: (res: SubtitleResponse) => {
        this.activeJobId.set(res.job_id);
        if (res.status === 'completed') {
          if (res.burned_in_video) {
            this.enableBurnedInVideo.set(true);
          }
          this.handleJobCompletion(res);
        } else if (res.status === 'failed') {
          this.handleJobFailure(
            res.error_message || 'Subtitle generation failed.',
          );
        } else {
          this.isProcessing.set(true);
          this.startPollingStatus(res.job_id);
        }
      },
      error: (err: HttpErrorResponse | Error | unknown) => {
        // If the browser already has previewVideoUrl from route params, remain in completed preview state
        if (this.previewVideoUrl()) {
          this.processingStep.set('completed');
          this.progressPercentage.set(100);
          this.isProcessing.set(false);
        } else {
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Subtitle job not found.';
          this.handleJobFailure(detail || 'Subtitle job not found.');
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.cleanupPreviewUrl();
  }

  private cleanupPreviewUrl(): void {
    const currentSrc = this.sourceVideoPreviewUrl();
    if (
      isPlatformBrowser(this.platformId) &&
      currentSrc &&
      currentSrc.startsWith('blob:')
    ) {
      try {
        window.URL.revokeObjectURL(currentSrc);
      } catch (err) {
        console.debug('Failed to revoke source object URL', err);
      }
    }
    const currentSub = this.subtitledVideoPreviewUrl();
    if (
      isPlatformBrowser(this.platformId) &&
      currentSub &&
      currentSub.startsWith('blob:')
    ) {
      try {
        window.URL.revokeObjectURL(currentSub);
      } catch (err) {
        console.debug('Failed to revoke subtitled object URL', err);
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

  private validateFileSize(file: File): boolean {
    const maxBytes = 500 * 1024 * 1024;
    if (file.size > maxBytes) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      this.errorMessage.set(
        `Selected file (${sizeMb} MB) exceeds maximum allowed size of 500 MB.`,
      );
      return false;
    }
    this.errorMessage.set(null);
    return true;
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      if (!this.validateFileSize(file)) {
        input.value = '';
        return;
      }
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(objUrl);
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

    dialogRef
      .afterClosed()
      .subscribe((result: Record<string, unknown> | null) => {
        if (result) {
          let title = 'Selected Gallery Asset';
          let url = '';
          if ('original_filename' in result && result['original_filename']) {
            title = String(result['original_filename']);
            url = String(result['gcs_uri'] || '');
          } else if ('mediaItem' in result && result['mediaItem']) {
            const item = result['mediaItem'] as Record<string, unknown>;
            title = String(
              item['title'] || item['filename'] || 'Gallery Video',
            );
            url = String(item['gcs_uri'] || item['url'] || '');
          } else if (typeof result === 'object' && result['title']) {
            title = String(result['title']);
            url = String(result['url'] || result['gcs_uri'] || '');
          }
          if (url) {
            this.selectGalleryAsset({
              id: String(result['id'] || 'gallery-selected'),
              title: title || 'Media Gallery Video',
              url: url,
            });
          } else {
            this.errorMessage.set(
              'Selected asset does not contain a playable video URL.',
            );
          }
        }
      });
  }

  selectGalleryAsset(asset: {id: string; title: string; url: string}): void {
    this.cleanupPreviewUrl();
    this.selectedGalleryAsset.set(asset);
    this.sourceVideoPreviewUrl.set(asset.url);
    this.subtitledVideoPreviewUrl.set(null);
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
      this.sourceVideoPreviewUrl.set(url.trim());
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(url.trim());
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
      if (!this.validateFileSize(file)) {
        return;
      }
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(objUrl);
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
    this.sourceVideoPreviewUrl.set(null);
    this.subtitledVideoPreviewUrl.set(null);
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
              if (consecutiveErrors >= 8) {
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

    if (res.job_id) {
      this.activeJobId.set(res.job_id);
      const isBurned = res.burned_in_video || this.enableBurnedInVideo();
      const videoFileType = isBurned ? 'burned_in_video' : 'toggleable_video';

      let streamUrl: string | null = null;
      if (res.burned_in_video && res.burned_in_video.startsWith('http')) {
        streamUrl = res.burned_in_video;
      } else if (
        res.processed_video_url &&
        res.processed_video_url.startsWith('http')
      ) {
        streamUrl = res.processed_video_url;
      } else if (
        res.default_toggleable_video &&
        res.default_toggleable_video.startsWith('http')
      ) {
        streamUrl = res.default_toggleable_video;
      } else {
        streamUrl = this.subtitlesService.getDownloadUrl(
          res.job_id,
          videoFileType,
        );
      }

      this.subtitledVideoPreviewUrl.set(streamUrl);
      this.previewVideoUrl.set(streamUrl);

      if (!this.sourceVideoPreviewUrl()) {
        const sourceUrl =
          res.source_video_path && res.source_video_path.startsWith('http')
            ? res.source_video_path
            : this.subtitlesService.getDownloadUrl(res.job_id, 'source_video');
        this.sourceVideoPreviewUrl.set(sourceUrl);
      }

      setTimeout(() => {
        if (isPlatformBrowser(this.platformId)) {
          if (this.burnedVideoPlayerRef?.nativeElement) {
            this.burnedVideoPlayerRef.nativeElement.load();
          }
          if (this.sourceVideoPlayerRef?.nativeElement) {
            this.sourceVideoPlayerRef.nativeElement.load();
          }
        }
      }, 50);
    }
  }

  private handleJobFailure(errorMsg: string): void {
    this.processingStep.set('failed');
    this.isProcessing.set(false);
    this.errorMessage.set(errorMsg);
  }

  onBurnedVideoError(event: Event): void {
    const currentUrl = this.subtitledVideoPreviewUrl();
    const jid = this.activeJobId();
    if (
      jid &&
      currentUrl &&
      !currentUrl.includes('/api/v1/custom/subtitles/download/')
    ) {
      console.warn(
        'Burned video stream playback error, attempting endpoint download fallback',
        event,
      );
      const fallbackUrl = this.subtitlesService.getDownloadUrl(
        jid,
        'burned_in_video',
      );
      this.subtitledVideoPreviewUrl.set(fallbackUrl);
    } else {
      console.warn('Burned video stream error event received:', event);
    }
  }

  onSourceVideoError(event: Event): void {
    const currentUrl = this.sourceVideoPreviewUrl();
    const jid = this.activeJobId();
    if (
      jid &&
      currentUrl &&
      !currentUrl.includes('/api/v1/custom/subtitles/download/')
    ) {
      console.warn(
        'Source video stream playback error, attempting endpoint download fallback',
        event,
      );
      const fallbackUrl = this.subtitlesService.getDownloadUrl(
        jid,
        'source_video',
      );
      this.sourceVideoPreviewUrl.set(fallbackUrl);
    } else {
      console.warn('Source video stream error event received:', event);
    }
  }

  readonly isSavingToGallery = signal<boolean>(false);
  readonly savedAssetId = signal<number | null>(null);
  readonly savedItemsCount = signal<number>(0);
  readonly savedFilenames = signal<string[]>([]);
  readonly isDownloadingFile = signal<string | null>(null);

  private triggerBrowserDownload(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (document.body.contains(a)) {
        document.body.removeChild(a);
      }
      window.URL.revokeObjectURL(url);
    }, 2000);
  }

  downloadCaptions(type: 'vtt' | 'srt'): void {
    const jobId = this.activeJobId();
    if (
      !jobId ||
      !isPlatformBrowser(this.platformId) ||
      this.isDownloadingFile()
    )
      return;

    this.isDownloadingFile.set(type);
    this.subtitlesService.downloadFile(jobId, type).subscribe({
      next: blob => {
        this.isDownloadingFile.set(null);
        this.triggerBrowserDownload(
          blob,
          `${this.currentPackageDisplayName()}.${type}`,
        );
      },
      error: async err => {
        this.isDownloadingFile.set(null);
        let msg = err?.message || 'Server error';
        if (err?.error instanceof Blob) {
          try {
            const parsed = JSON.parse(await err.error.text());
            msg = parsed?.detail || msg;
          } catch {
            // fallback
          }
        }
        this.errorMessage.set(`Failed to download .${type} file: ${msg}`);
      },
    });
  }

  downloadVideo(): void {
    const jobId = this.activeJobId();
    if (
      !jobId ||
      !isPlatformBrowser(this.platformId) ||
      this.isDownloadingFile()
    )
      return;

    this.isDownloadingFile.set('video');
    const fileType = this.enableBurnedInVideo()
      ? 'burned_in_video'
      : 'toggleable_video';
    this.subtitlesService.downloadFile(jobId, fileType).subscribe({
      next: blob => {
        this.isDownloadingFile.set(null);
        const suffix = this.enableBurnedInVideo() ? ' (Burned)' : '';
        this.triggerBrowserDownload(
          blob,
          `${this.currentPackageDisplayName()}${suffix}.mp4`,
        );
      },
      error: async err => {
        this.isDownloadingFile.set(null);
        let msg = err?.message || 'Server error';
        if (err?.error instanceof Blob) {
          try {
            const parsed = JSON.parse(await err.error.text());
            msg = parsed?.detail || msg;
          } catch {
            // fallback
          }
        }
        this.errorMessage.set(`Failed to download MP4 video: ${msg}`);
      },
    });
  }

  saveToMediaGallery(): void {
    const jobId = this.activeJobId();
    if (!jobId || this.isSavingToGallery()) return;

    const pkgName = this.currentPackageDisplayName();
    const rawWorkspaceId = this.workspaceStateService.getActiveWorkspaceId();
    const workspaceId = rawWorkspaceId ? Number(rawWorkspaceId) : null;

    this.isSavingToGallery.set(true);
    this.subtitlesService.saveToGallery(jobId, workspaceId, pkgName).subscribe({
      next: res => {
        this.isSavingToGallery.set(false);
        this.savedPackageName.set(res.asset_name || pkgName);
        this.savedAssetId.set(res.asset_id ?? null);
        this.savedItemsCount.set(res.saved_items_count || 1);
        this.savedFilenames.set(res.saved_filenames || []);
        this.savedToGallery.set(true);
      },
      error: err => {
        this.isSavingToGallery.set(false);
        const detail =
          err && typeof err === 'object' && 'error' in err
            ? (err as {error?: {detail?: string}}).error?.detail
            : err instanceof Error
              ? err.message
              : 'Failed to save creation to Media Gallery.';
        this.errorMessage.set(
          detail || 'Failed to save creation to Media Gallery.',
        );
      },
    });
  }
}
