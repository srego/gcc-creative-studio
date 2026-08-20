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

import {CommonModule} from '@angular/common';
import {Component, OnInit} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MatCardModule} from '@angular/material/card';
import {MatIconModule} from '@angular/material/icon';
import {MatInputModule} from '@angular/material/input';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {AdkAssistantService} from './adk-assistant.service';

@Component({
  selector: 'app-adk-assistant',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './adk-assistant.component.html',
  styleUrls: ['./adk-assistant.component.scss'],
})
export class AdkAssistantComponent implements OnInit {
  status = 'Initializing...';
  prompt = '';
  response = '';
  isLoading = false;

  constructor(private readonly adkService: AdkAssistantService) {}

  ngOnInit(): void {
    this.adkService.checkHealth().subscribe({
      next: res => {
        this.status = res.status === 'ok' ? 'Connected' : 'Degraded';
      },
      error: () => {
        this.status = 'Disconnected';
      },
    });
  }

  sendQuery(): void {
    if (!this.prompt.trim() || this.isLoading) {
      return;
    }
    this.isLoading = true;
    this.adkService.query(this.prompt).subscribe({
      next: res => {
        this.response = res.response;
        this.isLoading = false;
      },
      error: err => {
        this.response = `Error: ${err.message || 'Failed to query ADK Assistant'}`;
        this.isLoading = false;
      },
    });
  }
}
