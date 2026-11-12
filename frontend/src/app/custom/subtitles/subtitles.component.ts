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

import {CommonModule, isPlatformBrowser} from '@angular/common';
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
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MatDialog, MatDialogModule} from '@angular/material/dialog';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatTooltipModule} from '@angular/material/tooltip';
import {ActivatedRoute, RouterModule} from '@angular/router';
import {Subscription, timer, of, throwError} from 'rxjs';
import {switchMap, catchError} from 'rxjs/operators';
import {ImageSelectorComponent} from '../../common/components/image-selector/image-selector.component';
import {WorkspaceStateService} from '../../services/workspace/workspace-state.service';
import {
  SubtitlesService,
  SubtitleCue,
  SubtitleResponse,
} from './subtitles.service';

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
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    RouterModule,
  ],
  templateUrl: './subtitles.component.html',
  styleUrls: ['./subtitles.component.scss'],
})
export class SubtitlesComponent implements OnInit, OnDestroy {
  private destroyRef = inject(DestroyRef);

  @ViewChild('sourceVideoPlayer')
  sourceVideoPlayerRef?: ElementRef<HTMLVideoElement>;
  @ViewChild('softVideoPlayer')
  softVideoPlayerRef?: ElementRef<HTMLVideoElement>;
  @ViewChild('burnedVideoPlayer')
  burnedVideoPlayerRef?: ElementRef<HTMLVideoElement>;

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
    previewUrl?: string | null;
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

  // Processing & Video Preview Signals (Independent per Requested Output!)
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<SubtitleStep>('idle');
  readonly progressPercentage = signal<number>(0);
  readonly isDraggingOver = signal<boolean>(false);

  readonly sourceVideoPreviewUrl = signal<string | null>(null);
  readonly softVideoPreviewUrl = signal<string | null>(null);
  readonly burnedVideoPreviewUrl = signal<string | null>(null);
  readonly showOriginalSourcePostRun = signal<boolean>(false);

  // Interactive Cue List & Soft Overlay Signals
  readonly softCcEnabled = signal<boolean>(true);
  readonly editableCues = signal<SubtitleCue[]>([]);
  readonly activeCueIndex = signal<number>(-1);
  readonly activeCueText = signal<string>('');
  readonly cuesDirty = signal<boolean>(false);
  readonly isSavingCues = signal<boolean>(false);
  readonly isReburningVideo = signal<boolean>(false);
  readonly cueSaveMessage = signal<string | null>(null);

  // Persistence & Download Signals
  readonly savedToGallery = signal<boolean>(false);
  readonly savedPackageName = signal<string>('');
  readonly localOutputDir = signal<string | null>(null);
  readonly activeJobId = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly isSavingToGallery = signal<boolean>(false);
  readonly savedAssetId = signal<number | null>(null);
  readonly savedItemsCount = signal<number>(0);
  readonly savedFilenames = signal<string[]>([]);
  readonly isDownloadingFile = signal<string | null>(null);

  private pollSubscription?: Subscription;

  readonly statusDescription = computed(() => {
    switch (this.processingStep()) {
      case 'uploading':
        return 'Uploading source media to Cloud Storage...';
      case 'extracting':
        return 'Extracting 16kHz audio & detecting acoustic speech islands...';
      case 'transcribing':
        return 'Transcribing speech with STT v2 chirp_3 (Denoiser + Auto-Punctuation)...';
      case 'formatting':
        return 'Optimizing 2-line broadcast cues via Viterbi dynamic programming...';
      case 'packaging':
        return 'Exporting WebVTT/SRT sidecars & rendering requested video streams...';
      case 'completed':
        return 'Subtitle package generated!';
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
      const cleaned = this.videoUrl().trim().split('/').pop() || 'Web Video';
      baseName = cleaned.replace(/\.[^/.]+$/, '') || 'Web Video';
    }
    const langCode = this.sourceLanguage().split('-')[0].toUpperCase();
    return `${baseName} - Subtitles [${langCode}]`;
  });

  readonly currentPackageDisplayName = computed(() => {
    return this.packageName().trim() || this.suggestedPackageName();
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
          this.sourceVideoPreviewUrl.set(this.toBrowserPreviewUrl(videoUrl));
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
            this.burnedVideoPreviewUrl.set(videoUrl);
          }
          if (gcsUri) {
            this.activeTab.set('gallery');
            this.selectedGalleryAsset.set({
              id: 'gallery_source',
              title: packageName || 'Gallery Video',
              url: gcsUri,
              previewUrl: videoUrl,
            });
          }
        } else if (gcsUri) {
          this.activeTab.set('gallery');
          const preview = this.toBrowserPreviewUrl(gcsUri);
          this.selectedGalleryAsset.set({
            id: 'gallery_source',
            title: packageName || 'Gallery Video',
            url: gcsUri,
            previewUrl: preview,
          });
          this.sourceVideoPreviewUrl.set(preview);
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
          this.enableBurnedInVideo.set(Boolean(res.burned_in_video));
          this.enableDynamicSubtitles.set(true);
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
        if (this.burnedVideoPreviewUrl() || this.softVideoPreviewUrl()) {
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
    this.cleanupPreviewUrls();
  }

  private cleanupPreviewUrls(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    for (const sig of [
      this.sourceVideoPreviewUrl,
      this.softVideoPreviewUrl,
      this.burnedVideoPreviewUrl,
    ]) {
      const val = sig();
      if (val && val.startsWith('blob:')) {
        try {
          window.URL.revokeObjectURL(val);
        } catch {
          // ignore
        }
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
      this.cleanupPreviewUrls();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.softVideoPreviewUrl.set(null);
      this.burnedVideoPreviewUrl.set(null);
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
      .subscribe((rawResult: Record<string, unknown> | unknown[] | null) => {
        const result = (
          Array.isArray(rawResult) ? rawResult[0] : rawResult
        ) as Record<string, unknown> | null;
        if (result) {
          let title = 'Selected Gallery Asset';
          let url = '';
          let previewUrl: string | null = null;

          if ('gcsUri' in result || 'originalFilename' in result) {
            title = String(
              result['originalFilename'] ||
                result['title'] ||
                'Media Gallery Video',
            );
            url = String(result['gcsUri'] || result['presignedUrl'] || '');
            previewUrl = String(
              result['presignedOriginalUrl'] || result['presignedUrl'] || '',
            );
          } else if (
            'original_filename' in result &&
            result['original_filename']
          ) {
            title = String(result['original_filename']);
            url = String(result['gcs_uri'] || result['url'] || '');
            previewUrl = String(result['presigned_url'] || result['url'] || '');
          } else if ('mediaItem' in result && result['mediaItem']) {
            const item = result['mediaItem'] as Record<string, unknown>;
            const idx =
              typeof result['selectedIndex'] === 'number'
                ? result['selectedIndex']
                : 0;
            const titles = Array.isArray(item['titles'])
              ? (item['titles'] as string[])
              : [];
            const gcsUris = Array.isArray(item['gcsUris'])
              ? (item['gcsUris'] as string[])
              : [];
            const presignedUrls = Array.isArray(item['presignedUrls'])
              ? (item['presignedUrls'] as string[])
              : [];
            title = String(
              titles[idx] ||
                item['title'] ||
                item['filename'] ||
                item['prompt'] ||
                'Gallery Video',
            );
            url = String(
              gcsUris[idx] ||
                gcsUris[0] ||
                item['gcs_uri'] ||
                item['url'] ||
                presignedUrls[idx] ||
                '',
            );
            previewUrl = String(
              presignedUrls[idx] ||
                presignedUrls[0] ||
                item['presigned_url'] ||
                item['url'] ||
                '',
            );
          } else if (typeof result === 'object' && result['title']) {
            title = String(result['title']);
            url = String(
              result['gcsUri'] || result['gcs_uri'] || result['url'] || '',
            );
            previewUrl = String(
              result['presignedUrl'] || result['url'] || '',
            );
          }

          if (url) {
            this.selectGalleryAsset({
              id: String(result['id'] || 'gallery-selected'),
              title: title || 'Media Gallery Video',
              url,
              previewUrl:
                previewUrl && previewUrl.startsWith('http')
                  ? previewUrl
                  : this.toBrowserPreviewUrl(url),
            });
          } else {
            this.errorMessage.set(
              'Selected asset does not contain a playable video URL.',
            );
          }
        }
      });
  }

  private toBrowserPreviewUrl(rawUrl: string | null | undefined): string | null {
    if (!rawUrl) return null;
    const trimmed = rawUrl.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith('blob:')) return trimmed;
    if (trimmed.startsWith('gs://')) {
      const withoutScheme = trimmed.slice(5);
      const slashIdx = withoutScheme.indexOf('/');
      if (slashIdx <= 0) return null;
      const bucket = withoutScheme.slice(0, slashIdx);
      const objectPath = withoutScheme
        .slice(slashIdx + 1)
        .split('/')
        .map(seg => encodeURIComponent(seg))
        .join('/');
      return `https://storage.googleapis.com/${bucket}/${objectPath}`;
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      const lower = trimmed.toLowerCase();
      if (
        lower.includes('youtube.com/watch') ||
        lower.includes('youtu.be/') ||
        lower.includes('youtube.com/shorts/')
      ) {
        return null;
      }
      return trimmed;
    }
    return null;
  }

  selectGalleryAsset(asset: {
    id: string;
    title: string;
    url: string;
    previewUrl?: string | null;
  }): void {
    this.cleanupPreviewUrls();
    const resolvedPreview =
      asset.previewUrl || this.toBrowserPreviewUrl(asset.url);
    this.selectedGalleryAsset.set(asset);
    this.sourceVideoPreviewUrl.set(resolvedPreview);
    this.softVideoPreviewUrl.set(null);
    this.burnedVideoPreviewUrl.set(null);
    this.selectedFile.set(null);
    this.videoUrl.set('');
  }

  onUrlChange(url: string): void {
    this.videoUrl.set(url);
    if (url.trim()) {
      this.cleanupPreviewUrls();
      this.selectedFile.set(null);
      this.selectedGalleryAsset.set(null);
      const browserUrl = this.toBrowserPreviewUrl(url);
      this.sourceVideoPreviewUrl.set(browserUrl);
      this.softVideoPreviewUrl.set(null);
      this.burnedVideoPreviewUrl.set(null);
    } else {
      this.sourceVideoPreviewUrl.set(null);
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
      this.cleanupPreviewUrls();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.softVideoPreviewUrl.set(null);
      this.burnedVideoPreviewUrl.set(null);
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

  toggleOriginalSourcePostRun(): void {
    this.showOriginalSourcePostRun.update(val => !val);
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
    this.cleanupPreviewUrls();
    this.selectedFile.set(null);
    this.selectedGalleryAsset.set(null);
    this.videoUrl.set('');
    this.packageName.set('');
    this.sourceVideoPreviewUrl.set(null);
    this.softVideoPreviewUrl.set(null);
    this.burnedVideoPreviewUrl.set(null);
    this.showOriginalSourcePostRun.set(false);
    this.softCcEnabled.set(true);
    this.editableCues.set([]);
    this.activeCueIndex.set(-1);
    this.activeCueText.set('');
    this.cuesDirty.set(false);
    this.isSavingCues.set(false);
    this.isReburningVideo.set(false);
    this.cueSaveMessage.set(null);
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
    this.cuesDirty.set(false);
    this.cueSaveMessage.set(null);

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
        stylePreset: this.subtitleStylePreset(),
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

  toggleSoftCc(): void {
    this.softCcEnabled.update(val => !val);
  }

  formatTimestamp(sec: number): string {
    const safe = Math.max(0, Number(sec) || 0);
    const hrs = Math.floor(safe / 3600);
    const mins = Math.floor((safe % 3600) / 60);
    const secs = (safe % 60).toFixed(1).padStart(4, '0');
    if (hrs > 0) {
      return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${secs}`;
    }
    return `${String(mins).padStart(2, '0')}:${secs}`;
  }

  maxLineLength(text: string): number {
    if (!text) return 0;
    return Math.max(...text.split('\n').map(l => l.length), 0);
  }

  trackByCueIndex(index: number): number {
    return index;
  }

  seekToCue(cue: SubtitleCue, idx: number): void {
    this.activeCueIndex.set(idx);
    this.activeCueText.set(cue.text);
    const player =
      (this.enableDynamicSubtitles()
        ? this.softVideoPlayerRef?.nativeElement
        : null) || this.burnedVideoPlayerRef?.nativeElement;
    if (player) {
      player.currentTime = Math.max(0, cue.start_time + 0.03);
      player.play().catch(() => {
        // Autoplay policy if muted/uninteracted; seeking alone still updates frame
      });
    }
  }

  onCueTextChange(idx: number, newText: string): void {
    const list = this.editableCues();
    if (idx < 0 || idx >= list.length) return;
    list[idx].text = newText;
    this.cuesDirty.set(true);
    this.cueSaveMessage.set(null);
    if (this.activeCueIndex() === idx) {
      this.activeCueText.set(newText);
    }
  }

  saveCueEdits(reburnVideo = false): void {
    const jobId = this.activeJobId();
    if (!jobId || this.isSavingCues() || this.isReburningVideo()) return;

    if (reburnVideo) {
      this.isReburningVideo.set(true);
    } else {
      this.isSavingCues.set(true);
    }
    this.cueSaveMessage.set(null);
    this.errorMessage.set(null);

    this.subtitlesService
      .updateJobCues(jobId, this.editableCues(), reburnVideo)
      .subscribe({
        next: (res: SubtitleResponse) => {
          this.isSavingCues.set(false);
          this.isReburningVideo.set(false);
          this.cuesDirty.set(false);
          if (res.cues && res.cues.length > 0) {
            this.editableCues.set(res.cues.map(c => ({...c})));
          }
          if (
            reburnVideo &&
            res.burned_in_video &&
            res.burned_in_video.startsWith('http')
          ) {
            this.burnedVideoPreviewUrl.set(res.burned_in_video);
            setTimeout(() => {
              this.burnedVideoPlayerRef?.nativeElement?.load();
            }, 50);
            this.cueSaveMessage.set(
              'Saved caption edits and re-burned MP4 video!',
            );
          } else {
            this.cueSaveMessage.set(
              'Saved caption edits to .VTT and .SRT files!',
            );
          }
        },
        error: err => {
          this.isSavingCues.set(false);
          this.isReburningVideo.set(false);
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Failed to save caption edits.';
          this.errorMessage.set(detail || 'Failed to save caption edits.');
        },
      });
  }

  onSoftVideoTimeUpdate(event: Event): void {
    const videoEl = event.target as HTMLVideoElement | null;
    if (!videoEl) return;
    const t = videoEl.currentTime;
    const cues = this.editableCues();
    for (let i = 0; i < cues.length; i++) {
      const cue = cues[i];
      if (t >= cue.start_time && t <= cue.end_time) {
        if (this.activeCueIndex() !== i) {
          this.activeCueIndex.set(i);
        }
        if (this.activeCueText() !== cue.text) {
          this.activeCueText.set(cue.text);
        }
        return;
      }
    }
    if (this.activeCueIndex() !== -1) {
      this.activeCueIndex.set(-1);
    }
    if (this.activeCueText()) {
      this.activeCueText.set('');
    }
  }

  onBurnedVideoTimeUpdate(event: Event): void {
    // If only Burned-In Video was generated, still highlight the active cue in the editor!
    if (this.enableDynamicSubtitles()) return;
    const videoEl = event.target as HTMLVideoElement | null;
    if (!videoEl) return;
    const t = videoEl.currentTime;
    const cues = this.editableCues();
    for (let i = 0; i < cues.length; i++) {
      if (t >= cues[i].start_time && t <= cues[i].end_time) {
        if (this.activeCueIndex() !== i) {
          this.activeCueIndex.set(i);
        }
        return;
      }
    }
    if (this.activeCueIndex() !== -1) {
      this.activeCueIndex.set(-1);
    }
  }

  private parseVttTime(ts: string): number {
    const clean = ts.trim().replace(',', '.');
    const parts = clean.split(':');
    if (parts.length === 3) {
      return (
        parseFloat(parts[0]) * 3600 +
        parseFloat(parts[1]) * 60 +
        parseFloat(parts[2])
      );
    }
    if (parts.length === 2) {
      return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
    }
    return 0;
  }

  private parseWebVtt(vttContent: string): SubtitleCue[] {
    const blocks = vttContent.replace(/\r\n/g, '\n').split(/\n\s*\n/);
    const cues: SubtitleCue[] = [];
    let idx = 1;
    for (const block of blocks) {
      const lines = block
        .split('\n')
        .map(l => l.trim())
        .filter(Boolean);
      if (!lines.length || lines[0].startsWith('WEBVTT')) continue;
      const arrowLineIdx = lines.findIndex(l => l.includes('-->'));
      if (arrowLineIdx === -1) continue;
      const [rawStart, rawEndWithSettings] = lines[arrowLineIdx].split('-->');
      const rawEnd = (rawEndWithSettings || '').trim().split(/\s+/)[0];
      const start_time = this.parseVttTime(rawStart);
      const end_time = this.parseVttTime(rawEnd);
      const text = lines.slice(arrowLineIdx + 1).join('\n').trim();
      if (text && end_time >= start_time) {
        cues.push({index: idx++, start_time, end_time, text});
      }
    }
    return cues;
  }

  private loadCuesFallback(jobId: string): void {
    this.subtitlesService.getJobCues(jobId).subscribe({
      next: cues => {
        if (cues && cues.length > 0) {
          this.editableCues.set(cues.map(c => ({...c})));
          return;
        }
        this.subtitlesService.downloadFile(jobId, 'vtt').subscribe({
          next: async blob => {
            try {
              const text = await blob.text();
              this.editableCues.set(this.parseWebVtt(text));
            } catch (e) {
              console.warn('Failed to parse WebVTT cues fallback:', e);
            }
          },
        });
      },
      error: () => {
        this.subtitlesService.downloadFile(jobId, 'vtt').subscribe({
          next: async blob => {
            try {
              const text = await blob.text();
              this.editableCues.set(this.parseWebVtt(text));
            } catch (e) {
              console.warn('Failed to parse WebVTT cues fallback:', e);
            }
          },
        });
      },
    });
  }

  private fetchAuthenticatedVideoBlobUrl(
    jobId: string,
    fileType: 'burned_in_video' | 'toggleable_video' | 'source_video',
    targetSignal: typeof this.sourceVideoPreviewUrl,
    playerRef?: ElementRef<HTMLVideoElement>,
  ): void {
    if (!isPlatformBrowser(this.platformId)) return;
    this.subtitlesService.downloadFile(jobId, fileType).subscribe({
      next: blob => {
        const objUrl = window.URL.createObjectURL(blob);
        targetSignal.set(objUrl);
        setTimeout(() => {
          playerRef?.nativeElement?.load();
        }, 50);
      },
      error: err => {
        console.warn(`Authenticated fallback fetch for ${fileType} failed:`, err);
      },
    });
  }

  private handleJobCompletion(res: SubtitleResponse): void {
    this.processingStep.set('completed');
    this.progressPercentage.set(100);
    this.isProcessing.set(false);
    this.localOutputDir.set(res.local_output_dir || null);
    this.activeCueIndex.set(-1);
    this.activeCueText.set('');
    this.cuesDirty.set(false);

    if (res.job_id) {
      this.activeJobId.set(res.job_id);

      // 1. Load structured timestamped cues for the Cue Editor & Soft Overlay
      if (res.cues && res.cues.length > 0) {
        this.editableCues.set(res.cues.map(c => ({...c})));
      } else {
        this.loadCuesFallback(res.job_id);
      }

      // 2. Original Source Video URL
      const existingSource = this.sourceVideoPreviewUrl();
      const resolvedSourceHttp =
        res.source_video_path && res.source_video_path.startsWith('http')
          ? res.source_video_path
          : null;
      if (!existingSource || !existingSource.startsWith('blob:')) {
        if (resolvedSourceHttp) {
          this.sourceVideoPreviewUrl.set(resolvedSourceHttp);
        } else {
          this.fetchAuthenticatedVideoBlobUrl(
            res.job_id,
            'source_video',
            this.sourceVideoPreviewUrl,
            this.sourceVideoPlayerRef,
          );
        }
      }

      // 3. Dynamic Subtitles Preview (Not Burned-In) — populated if requested!
      if (this.enableDynamicSubtitles()) {
        this.softCcEnabled.set(true);
        const softHttp =
          (res.default_toggleable_video &&
          res.default_toggleable_video.startsWith('http')
            ? res.default_toggleable_video
            : null) ||
          resolvedSourceHttp ||
          (existingSource && existingSource.startsWith('blob:')
            ? existingSource
            : null);

        if (softHttp) {
          this.softVideoPreviewUrl.set(softHttp);
        } else {
          this.fetchAuthenticatedVideoBlobUrl(
            res.job_id,
            'toggleable_video',
            this.softVideoPreviewUrl,
            this.softVideoPlayerRef,
          );
        }
      } else {
        this.softVideoPreviewUrl.set(null);
      }

      // 4. Burned-In Subtitled Video Preview (Static MP4) — populated if requested!
      if (this.enableBurnedInVideo()) {
        const burnedHttp =
          res.burned_in_video && res.burned_in_video.startsWith('http')
            ? res.burned_in_video
            : null;
        if (burnedHttp) {
          this.burnedVideoPreviewUrl.set(burnedHttp);
        } else {
          this.fetchAuthenticatedVideoBlobUrl(
            res.job_id,
            'burned_in_video',
            this.burnedVideoPreviewUrl,
            this.burnedVideoPlayerRef,
          );
        }
      } else {
        this.burnedVideoPreviewUrl.set(null);
      }

      setTimeout(() => {
        if (isPlatformBrowser(this.platformId)) {
          this.softVideoPlayerRef?.nativeElement?.load();
          this.burnedVideoPlayerRef?.nativeElement?.load();
          this.sourceVideoPlayerRef?.nativeElement?.load();
        }
      }, 50);
    }
  }

  private handleJobFailure(errorMsg: string): void {
    this.processingStep.set('failed');
    this.isProcessing.set(false);
    this.errorMessage.set(errorMsg);
  }

  onSoftVideoError(event: Event): void {
    const currentUrl = this.softVideoPreviewUrl();
    const jid = this.activeJobId();
    if (jid && currentUrl && !currentUrl.startsWith('blob:')) {
      console.warn(
        'Soft video stream error, attempting authenticated blob fallback',
        event,
      );
      this.fetchAuthenticatedVideoBlobUrl(
        jid,
        'toggleable_video',
        this.softVideoPreviewUrl,
        this.softVideoPlayerRef,
      );
    }
  }

  onBurnedVideoError(event: Event): void {
    const currentUrl = this.burnedVideoPreviewUrl();
    const jid = this.activeJobId();
    if (jid && currentUrl && !currentUrl.startsWith('blob:')) {
      console.warn(
        'Burned video stream error, attempting authenticated blob fallback',
        event,
      );
      this.fetchAuthenticatedVideoBlobUrl(
        jid,
        'burned_in_video',
        this.burnedVideoPreviewUrl,
        this.burnedVideoPlayerRef,
      );
    }
  }

  onSourceVideoError(event: Event): void {
    const currentUrl = this.sourceVideoPreviewUrl();
    const jid = this.activeJobId();
    if (jid && currentUrl && !currentUrl.startsWith('blob:')) {
      this.fetchAuthenticatedVideoBlobUrl(
        jid,
        'source_video',
        this.sourceVideoPreviewUrl,
        this.sourceVideoPlayerRef,
      );
    }
  }

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

  downloadBurnedVideo(): void {
    const jobId = this.activeJobId();
    if (
      !jobId ||
      !isPlatformBrowser(this.platformId) ||
      this.isDownloadingFile()
    )
      return;

    this.isDownloadingFile.set('video');
    this.subtitlesService.downloadFile(jobId, 'burned_in_video').subscribe({
      next: blob => {
        this.isDownloadingFile.set(null);
        this.triggerBrowserDownload(
          blob,
          `${this.currentPackageDisplayName()} (Burned).mp4`,
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
