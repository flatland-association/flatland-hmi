import {Component, OnInit} from '@angular/core'
import {StateService} from '../state.service'
import {combineLatest} from 'rxjs'

@Component({
  selector: 'app-replay-badge',
  imports: [],
  templateUrl: './replay-badge.component.html',
  styleUrl: './replay-badge.component.scss',
})
export class ReplayBadgeComponent implements OnInit {
  public replaying = false
  /** True once the replay cursor has moved past the actual history — i.e. showing a predicted plan snapshot
   * rather than a real past step. Rendered as "FUTURE" instead of "REPLAY", same red styling as REPLAY. */
  public future = false

  constructor(private stateService: StateService) {
  }

  ngOnInit() {
    combineLatest([this.stateService.getReplayTime(), this.stateService.getHistory()]).subscribe(
      ([replayTime, history]) => {
        this.replaying = replayTime !== null
        this.future = replayTime !== null && replayTime > history.length
      },
    )
  }
}
