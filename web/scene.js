import { visualGroundCorrection } from "./model-alignment.mjs";
import { NavigationMap } from "./navigation-map.mjs";
import { AirfieldView } from "./airfield.js";
import { WorldStreamer, CesiumWorldHost } from "./world/index.js";
import { aircraftBasis } from "./flight-math.mjs";
import { DebugCamera } from "./debug-camera.js";
const C = window.Cesium;
const color = (value) => C.Color.fromCssColorString(value);

export class FlightScene {
  constructor(settings) {
    this.physicalGroundM = settings.ground_m;
    this.geoidSeparationM = settings.geoid_separation_m ?? 0;
    settings = {...settings, ground_m:settings.ground_m + this.geoidSeparationM};
    this.settings = settings;
    this.view = "chase";
    this.followMap = true;
    this.main = this.viewer("camera-globe");
    this.map = this.viewer("map-globe");
    this.position = C.Cartesian3.fromDegrees(
      settings.home[0],
      settings.home[1],
      settings.ground_m + 2,
    );
    this.orientation = new C.Quaternion();
    this.matrix = new C.Matrix4();
    this.rotation = new C.Matrix3();
    this.scratch = new C.Cartesian3();
    this.path = [];
    this.mapAircraftHeading = C.Math.toRadians(settings.heading_deg ?? 0);
    this.marker = this.map.entities.add({
      position: this.position,
      billboard: {
        image: "/assets/drone-marker.svg",
        width: 30,
        height: 30,
        rotation: new C.CallbackProperty(() => this.map.camera.heading - this.mapAircraftHeading, false),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    this.map.entities.add({
      polyline: {
        positions: new C.CallbackProperty(() => this.path, false),
        width: 2,
        material: color("#d5ffad"),
      },
    });
    this.aircraft = this.main.entities.add({
      position: this.position,
      orientation: this.orientation,
      billboard: {
        show: new C.CallbackProperty(() => this.view === "orbit", false),
        image: "/assets/debug-aircraft-marker.svg",
        width: 28,
        height: 28,
        rotation: new C.CallbackProperty(() => this.main.camera.heading - this.mapAircraftHeading, false),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        show: new C.CallbackProperty(() => this.view === "orbit", false),
        text: "▼ САМОЛЁТ · DEBUG",
        font: "bold 14px sans-serif",
        fillColor: color("#ffcf55"),
        outlineColor: C.Color.BLACK,
        outlineWidth: 2,
        style: C.LabelStyle.FILL_AND_OUTLINE,
        showBackground: true,
        backgroundColor: color("#10262de6"),
        pixelOffset: new C.Cartesian2(0, -30),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      model: {
        uri: "/data/aircraft.glb",
        scale: 0.11,
        shadows: C.ShadowMode.ENABLED,
      },
    });
    this.main.camera.setView({
      destination: C.Cartesian3.fromDegrees(
        settings.home[0],
        settings.home[1] - 0.003,
        settings.ground_m + 230,
      ),
      orientation: { heading: 0, pitch: -0.55, roll: 0 },
    });
    this.airfield = new AirfieldView(this);
    this.centerMap();
  }

  viewer(id) {
    const viewer = new C.Viewer(id, {
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      shadows: true,
    });
    viewer.targetFrameRate = 60;
    viewer.scene.globe.baseColor = color("#879778");
    viewer.scene.skyAtmosphere.show = true;
    viewer.scene.fog.enabled = true;
    viewer.scene.postProcessStages.fxaa.enabled = true;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.light = new C.DirectionalLight({
      direction: new C.Cartesian3(0.3, 0.4, -1),
      intensity: 2,
    });
    C.TileMapServiceImageryProvider.fromUrl(
      "/vendor/cesium/Assets/Textures/NaturalEarthII",
      { maximumLevel: 2 },
    ).then((provider) => viewer.imageryLayers.addImageryProvider(provider));
    return viewer;
  }

  async loadMap() {
    const debugSettings = await fetch('/debug-camera.json').then(response => response.json());
    this.debugCamera = new DebugCamera(this.main, debugSettings, () => this.position);
    this.debugCamera.setActive(this.view === 'orbit');
    this.worldSettings = await fetch("/api/world/settings").then((r) =>
      r.json(),
    );
    const fleet = await fetch('/api/aircraft').then(r => r.json());
    const visual = fleet.aircraft.find(a => a.id === (this.settings.aircraft_id || fleet.selected))?.visual;
    if (visual) {
      this.aircraft.model.uri = visual.uri;
      if (visual.scale !== undefined) this.worldSettings.aircraft_visual_scale = visual.scale;
      if (visual.origin_up_m !== undefined) this.worldSettings.aircraft_visual_origin_up_m = visual.origin_up_m;
    }
    this.modelSupport = await fetch(visual?.support_uri || '/data/aircraft-support.json').then((r) =>
      r.json(),
    );
    this.navigation = new NavigationMap(this, this.worldSettings);
    this.aircraft.model.scale = this.worldSettings.aircraft_visual_scale;
    this.world = new WorldStreamer(new CesiumWorldHost({main:this.main, map:this.map, groundM:this.settings.ground_m}), this.worldSettings);
    if (this.streamingPreferences) this.world.configure(this.streamingPreferences);
    this.world.setDebug(this.showGrid);
    this.main.scene.preRender.addEventListener(()=>{
      if(this.view!=='orbit'||!this.debugCamera.streamingCheckbox.checked||!this.world)return;
      const now=performance.now();
      if(now-(this.lastCameraStreamingUpdate??-Infinity)<500)return;
      this.lastCameraStreamingUpdate=now;
      const camera=this.main.camera;
      const at=C.Cartographic.fromCartesian(camera.positionWC);
      const positions=[];
      if(this.lastStreamingAircraftPose)positions.push(this.lastStreamingAircraftPose);
      const target=camera.pickEllipsoid(new C.Cartesian2(this.main.canvas.clientWidth/2,this.main.canvas.clientHeight/2),C.Ellipsoid.WGS84);
      if(target){const p=C.Cartographic.fromCartesian(target);positions.push({longitude_deg:C.Math.toDegrees(p.longitude),latitude_deg:C.Math.toDegrees(p.latitude)});}
      this.world.update({longitude_deg:C.Math.toDegrees(at.longitude),latitude_deg:C.Math.toDegrees(at.latitude)},positions);
    });
    const bounds = C.Rectangle.fromDegrees(...this.worldSettings.bounds);
    // The overview uses the same Web Mercator scheme as the source, not a
    // geographic image rectangle that would distort latitude across the region.
    this.map.imageryLayers.addImageryProvider(
      new C.UrlTemplateImageryProvider({
        url: "/api/world/tile/{z}/{x}/{y}.jpg",
        tilingScheme: new C.WebMercatorTilingScheme(),
        minimumLevel: this.worldSettings.overview_level,
        maximumLevel: this.worldSettings.detail_level,
        rectangle: bounds,
        credit: this.worldSettings.credit,
      }),
    );
    this.world.update({
      longitude_deg: this.settings.home[0],
      latitude_deg: this.settings.home[1],
    });
    this.vision = "normal";
    this.night = false;
    this.sensor = this.main.scene.postProcessStages.add(
      new C.PostProcessStage({
        fragmentShader: `uniform sampler2D colorTexture; uniform sampler2D depthTexture; in vec2 v_textureCoordinates;
      float thermalSignal(vec2 uv) {
        float depth=czm_unpackDepth(texture(depthTexture,uv));
        if(depth==0.0 || depth>=1.0) return 0.025;
        vec3 source=texture(colorTexture,uv).rgb;
        float luminance=dot(source,vec3(.299,.587,.114));
        float vegetation=smoothstep(.005,.09,source.g-max(source.r,source.b))*(1.0-smoothstep(.18,.40,luminance));
        return mix(.12+.65*(1.0-luminance),.91,vegetation);
      }
      uniform float sensorMode; uniform float nightMode; uniform float nightBrightness;
      void main() {
        vec3 rgb=texture(colorTexture,v_textureCoordinates).rgb;
        float luminance=dot(rgb,vec3(0.299,0.587,0.114));
        if(sensorMode<0.5) rgb *= mix(1.0,nightBrightness,nightMode);
        else if(sensorMode<1.5) {
          float signal=pow(luminance,0.6);
          float vignette=clamp(1.2-length(v_textureCoordinates-0.5),0.35,1.0);
          rgb=vec3(0.12,1.0,0.22)*signal*vignette;
        } else if(sensorMode<2.5) rgb=vec3(smoothstep(0.05,0.85,luminance));
        else {
          vec2 pixel=1.4/czm_viewport.zw;
          float signal=.4*thermalSignal(v_textureCoordinates);
          signal+=.15*(thermalSignal(v_textureCoordinates+vec2(pixel.x,0.0))+thermalSignal(v_textureCoordinates-vec2(pixel.x,0.0))+thermalSignal(v_textureCoordinates+vec2(0.0,pixel.y))+thermalSignal(v_textureCoordinates-vec2(0.0,pixel.y)));
          float noise=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;
          rgb=vec3(clamp(signal+noise*.025,0.0,1.0));
        }
        out_FragColor=vec4(rgb,1.0);
      }`,
        uniforms: {
          sensorMode: () =>
            ({ normal: 0, night: 1, thermal: 2, thermal_soft: 3 })[this.vision],
          nightMode: () => (this.night ? 1 : 0),
          nightBrightness: () => this.worldSettings.night_light_intensity,
        },
      }),
    );
  }

  setVision(mode) {
    this.vision = mode;
  }
  setNight(night) {
    this.night = night;
    this.main.scene.skyAtmosphere.show = !night;
    this.main.scene.sun.show = !night;
    this.main.scene.backgroundColor = night
      ? C.Color.BLACK
      : C.Color.fromCssColorString("#729bbb");
  }

  setView(view) {
    if (view === "orbit" && this.view !== "orbit") {
      const location = C.Cartographic.fromCartesian(this.position);
      this.main.camera.setView({
        destination: C.Cartesian3.fromRadians(
          location.longitude,
          location.latitude,
          this.settings.ground_m + 6500,
        ),
        orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
      });
    }
    this.view = view;
    this.world?.setDebug(this.showGrid);
    this.main.scene.screenSpaceCameraController.enableInputs = false;
    this.debugCamera?.setActive(view === 'orbit');
  }

  centerMap() {
    this.followMap = true;
    const cartographic = C.Cartographic.fromCartesian(this.position);
    this.map.camera.setView({
      destination: C.Cartesian3.fromRadians(
        cartographic.longitude,
        cartographic.latitude,
        this.settings.ground_m + (this.navigation?.height ?? 700),
      ),
      orientation: { heading: this.navigation?.heading ?? 0, pitch: -Math.PI / 2, roll: 0 },
    });
  }

  update(pose) {
    C.Cartesian3.fromDegrees(
      pose.longitude_deg,
      pose.latitude_deg,
      pose.altitude_asl_m + this.geoidSeparationM,
      C.Ellipsoid.WGS84,
      this.position,
    );
    const heading = C.Math.toRadians(pose.yaw_deg);
    this.mapAircraftHeading = heading;
    const pitch = C.Math.toRadians(pose.pitch_deg);
    const roll = C.Math.toRadians(pose.roll_deg);
    const basis = aircraftBasis(heading, pitch, roll);
    const enu = C.Transforms.eastNorthUpToFixedFrame(this.position);
    const direction = C.Matrix4.multiplyByPointAsVector(
      enu,
      C.Cartesian3.fromArray(basis.forward),
      new C.Cartesian3(),
    );
    const up = C.Matrix4.multiplyByPointAsVector(
      enu,
      C.Cartesian3.fromArray(basis.up),
      new C.Cartesian3(),
    );
    const right = C.Matrix4.multiplyByPointAsVector(
      enu,
      C.Cartesian3.fromArray(basis.right),
      new C.Cartesian3(),
    );
    C.Matrix3.setColumn(this.rotation, 0, direction, this.rotation);
    C.Matrix3.setColumn(
      this.rotation,
      1,
      C.Cartesian3.negate(right, new C.Cartesian3()),
      this.rotation,
    );
    C.Matrix3.setColumn(this.rotation, 2, up, this.rotation);
    C.Quaternion.fromRotationMatrix(this.rotation, this.orientation);
    this.lastStreamingAircraftPose=pose;
    if(!(this.view==='orbit'&&this.debugCamera?.streamingCheckbox.checked))this.world?.update(pose);
    const visualPosition = C.Cartesian3.add(
      this.position,
      C.Cartesian3.multiplyByScalar(
        up,
        this.worldSettings?.aircraft_visual_origin_up_m ?? 0.1,
        new C.Cartesian3(),
      ),
      new C.Cartesian3(),
    );
    if (this.modelSupport) {
      const correction = visualGroundCorrection(
        pose,
        this.worldSettings,
        this.modelSupport.support_points,
      );
      if (correction > 0)
        C.Cartesian3.add(
          visualPosition,
          C.Matrix4.multiplyByPointAsVector(
            enu,
            new C.Cartesian3(0, 0, correction),
            new C.Cartesian3(),
          ),
          visualPosition,
        );
    }
    this.aircraft.position = visualPosition;
    this.aircraft.orientation = this.orientation;
    this.aircraft.show = this.view !== "cockpit";
    this.marker.position = this.position;
    if (
      !this.path.length ||
      C.Cartesian3.distance(this.path[this.path.length - 1], this.position) > 8
    ) {
      this.path.push(C.Cartesian3.clone(this.position));
      if (this.path.length > 1500) this.path.shift();
    }
    if (this.view === "cockpit") {
      const nose = C.Cartesian3.multiplyByScalar(
        direction,
        this.worldSettings?.camera_nose_offset_m ?? 1.8,
        new C.Cartesian3(),
      );
      C.Cartesian3.add(
        nose,
        C.Cartesian3.multiplyByScalar(
          up,
          this.worldSettings?.camera_vertical_offset_m ?? -0.1,
          new C.Cartesian3(),
        ),
        nose,
      );
      C.Cartesian3.add(this.position, nose, nose);
      this.main.camera.setView({
        destination: nose,
        orientation: { direction, up },
      });
    }
    if (this.view === "chase") {
      const transform = C.Transforms.eastNorthUpToFixedFrame(this.position);
      C.Matrix4.multiplyByPoint(
        transform,
        new C.Cartesian3(
          -Math.sin(heading) * (this.worldSettings?.chase_distance_m ?? 8),
          -Math.cos(heading) * (this.worldSettings?.chase_distance_m ?? 8),
          this.worldSettings?.chase_height_m ?? 2.5,
        ),
        this.scratch,
      );
      this.main.camera.setView({
        destination: this.scratch,
        orientation: { heading, pitch: -0.25, roll: 0 },
      });
    }
    if (this.navigation) this.navigation.update(pose);
    else if (this.followMap) this.centerMap();
  }
}
