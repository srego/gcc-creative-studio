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

import {Clipboard, ClipboardModule} from '@angular/cdk/clipboard';
import {CommonModule} from '@angular/common';
import {
  AfterViewChecked,
  Component,
  ElementRef,
  OnInit,
  ViewChild,
} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatTooltipModule} from '@angular/material/tooltip';
import {
  AdkAssistantService,
  ChatMessage,
} from './adk-assistant.service';

export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export interface QuickSuggestion {
  label: string;
  icon: string;
  prompt: string;
}

@Component({
  selector: 'app-adk-assistant',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ClipboardModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './adk-assistant.component.html',
  styleUrls: ['./adk-assistant.component.scss'],
})
export class AdkAssistantComponent implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  @ViewChild('promptInput') private promptInput?: ElementRef<HTMLTextAreaElement>;

  status: 'Online' | 'Connecting' | 'Offline' = 'Connecting';
  modelName = 'gemini-3.7-flash';
  serviceName = 'adk-assistant';
  sessionId = this.generateSessionId();
  prompt = '';
  isLoading = false;
  copiedMessageId: string | null = null;
  private shouldScrollToBottom = false;

  readonly quickSuggestions: QuickSuggestion[] = [
    {
      label: 'Optimize Imagen Prompt',
      icon: 'photo_camera',
      prompt:
        'Optimize this prompt for Imagen 3 photorealism: A modern studio portrait of a product designer in a glass architecture atelier during golden hour, 85mm lens, shallow depth of field, dramatic cinematic lighting.',
    },
    {
      label: 'Generate Veo Storyboard',
      icon: 'movie_filter',
      prompt:
        'Create a 4-shot cinematic video storyboard prompt sequence for Veo depicting an autonomous electric sports car navigating a futuristic neon city in rainy night with smooth drone tracking shots.',
    },
    {
      label: 'Brand Consistency Check',
      icon: 'verified',
      prompt:
        'Evaluate this campaign copy against Google Cloud brand guidelines: clean typography, inspiring tone, technological clarity, and human-centric benefits.',
    },
    {
      label: 'Multimodal Concept Ideas',
      icon: 'auto_awesome_motion',
      prompt:
        'Suggest 3 multimodal creative concept variations combining 4K hero stills with 5-second cinematic motion loops for a luxury eco-resort brand launch.',
    },
  ];

  messages: DisplayMessage[] = [
    {
      id: 'msg-init',
      role: 'assistant',
      content:
        'Welcome to Google Cloud Creative Studio AI Assistant! I can help you craft high-impact prompts for Imagen 3 and Veo, enforce brand consistency guidelines, structure storyboard narratives, and automate multimodal creative workflows. How can I assist your campaign today?',
      timestamp: new Date(),
    },
  ];

  constructor(
    private readonly adkService: AdkAssistantService,
    private readonly clipboard: Clipboard,
  ) {}

  ngOnInit(): void {
    this.checkHealth();
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  checkHealth(): void {
    this.status = 'Connecting';
    this.adkService.checkHealth().subscribe({
      next: res => {
        this.status = res.status === 'healthy' || res.status === 'ok' ? 'Online' : 'Online';
        if (res.model) {
          this.modelName = res.model;
        }
        if (res.service) {
          this.serviceName = res.service;
        }
      },
      error: () => {
        this.status = 'Offline';
      },
    });
  }

  sendMessage(customPrompt?: string): void {
    const textToSend = (customPrompt ?? this.prompt).trim();
    if (!textToSend || this.isLoading) {
      return;
    }

    const userMessage: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date(),
    };

    this.messages.push(userMessage);
    this.prompt = '';
    this.isLoading = true;
    this.shouldScrollToBottom = true;

    // Convert display messages to ChatMessage history
    const historyPayload: ChatMessage[] = this.messages.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp.toISOString(),
    }));

    this.adkService
      .sendMessage(textToSend, this.sessionId, historyPayload)
      .subscribe({
        next: res => {
          if (res.sessionId) {
            this.sessionId = res.sessionId;
          }
          const assistantMessage: DisplayMessage = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: res.response,
            timestamp: new Date(),
          };
          this.messages.push(assistantMessage);
          this.isLoading = false;
          this.shouldScrollToBottom = true;
        },
        error: err => {
          const errorMessage: DisplayMessage = {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: `⚠️ Error executing ADK Assistant query: ${
              err.error?.detail || err.message || 'Service temporarily unreachable.'
            }`,
            timestamp: new Date(),
          };
          this.messages.push(errorMessage);
          this.isLoading = false;
          this.shouldScrollToBottom = true;
        },
      });
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  applySuggestion(suggestionPrompt: string): void {
    this.prompt = suggestionPrompt;
    if (this.promptInput) {
      this.promptInput.nativeElement.focus();
    }
  }

  copyContent(content: string, id: string): void {
    this.clipboard.copy(content);
    this.copiedMessageId = id;
    setTimeout(() => {
      if (this.copiedMessageId === id) {
        this.copiedMessageId = null;
      }
    }, 2000);
  }

  resetSession(): void {
    this.sessionId = this.generateSessionId();
    this.messages = [
      {
        id: `msg-init-${Date.now()}`,
        role: 'assistant',
        content:
          'Session refreshed. Ready for your next creative generation, prompt refinement, or brand alignment query.',
        timestamp: new Date(),
      },
    ];
    this.prompt = '';
    this.shouldScrollToBottom = true;
    if (this.promptInput) {
      this.promptInput.nativeElement.focus();
    }
  }

  private scrollToBottom(): void {
    if (this.scrollContainer) {
      try {
        const el = this.scrollContainer.nativeElement;
        el.scrollTo({
          top: el.scrollHeight,
          behavior: 'smooth',
        });
      } catch {
        // Fallback for non-smooth scrolling
      }
    }
  }

  trackByMsgId(_index: number, msg: DisplayMessage): string {
    return msg.id;
  }

  private generateSessionId(): string {
    return 'cs-adk-' + Math.random().toString(36).substring(2, 11) + '-' + Date.now();
  }
}

