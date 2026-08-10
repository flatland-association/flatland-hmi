import {Component, OnInit} from '@angular/core'
import {StateService} from '../state.service'

@Component({
  selector: 'app-replay-badge',
  imports: [],
  templateUrl: './replay-badge.component.html',
  styleUrl: './replay-badge.component.scss',
})
export class ReplayBadgeComponent implements OnInit {
  public replaying = false

  constructor(private stateService: StateService) {
  }

  ngOnInit() {
    this.stateService.getReplayTime().subscribe((replayTime) => {
      this.replaying = replayTime !== null
    })
  }
}
