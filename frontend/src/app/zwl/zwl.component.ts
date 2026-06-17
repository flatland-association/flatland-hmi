import {Component, OnInit} from '@angular/core'
import {StateService} from '../state.service'
import {MapCell, RendererService} from '../renderer.service'
import {firstValueFrom} from 'rxjs'
import {Agent, DataService} from '../data.service'
import {FormsModule} from '@angular/forms'
import {ControllerService} from '../controller.service'

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-zwl',
  imports: [FormsModule],
  templateUrl: './zwl.component.html',
  styleUrl: './zwl.component.scss',
})
export class ZwlComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []

  public lineOptions: SelectOption[] = []
  public selectedLine = ''
  public mapping: Record<string, unknown> = {}
  public reverseMapping: Record<string, [number, number]> = {}
  public trajectoryId: string | null = null

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    private dataService: DataService,
    public controllerService: ControllerService,
  ) {
  }

  ngOnInit() {
    this.stateService.getTrajectoryId().subscribe((trajectoryId) => {
      this.trajectoryId = trajectoryId
    })
    this.stateService.getTransitions().subscribe(() => this.fetchLineTransitions())
    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
    })
  }

  private setMapping(mapping: Record<string, unknown>) {
    this.mapping = mapping
    this.reverseMapping = {}
    for (const [key, val] of Object.entries(mapping)) {
      if (Array.isArray(val) && val.length >= 2) {
        const match = key.match(/\((\d+), (\d+)\)/)
        if (match) {
          this.reverseMapping[`(${val[0]}, ${val[1]})`] = [parseInt(match[1]), parseInt(match[2])]
        }
      }
    }
  }

  public getOriginalPosition(zwlRow: number, zwlCol: number): [number, number] | null {
    return this.reverseMapping[`(${zwlRow}, ${zwlCol})`] ?? null
  }

  public getZwlPosition(x: number, y: number) {
    const key = `(${x}, ${y})`
    const val = this.mapping[key]
    console.log(`   ${key} --> ${val}   : ${this.mapping}`)
    if (Array.isArray(val) && val.length >= 2) {
      return [val[0] as number, val[1] as number]
    }
    return null
  }

  public onLineChange() {
    this.stateService.setSelectedLine(this.selectedLine)
    if (!this.trajectoryId) return
    this.fetchZwlForselectedLine(this.trajectoryId)
  }

  private fetchLineTransitions() {
    if (!this.trajectoryId) return
    this.dataService.getTrajectoryLines(this.trajectoryId).then((lines) => {
      this.lineOptions = lines.map((l, i) => ({
        value: String(i),
        label: l.label,
      }))
      if (!this.lineOptions.find(o => o.value === this.selectedLine)) {
        this.selectedLine = this.lineOptions[0]?.value ?? ''
      }
      if (!this.trajectoryId) return

      this.fetchZwlForselectedLine(this.trajectoryId)
    })
  }

  private fetchZwlForselectedLine(trajectoryId: string) {
    if (!this.selectedLine) return
    this.dataService.getTrajectoryLineTransitions(trajectoryId, this.selectedLine)
      .then(data =>
        firstValueFrom(this.stateService.getAgents()).then(agents => {
          this.mapClasses = this.rendererService.renderMap(data.grid, agents)
          this.setMapping(data.mapping)
        })
      )
  }
}
